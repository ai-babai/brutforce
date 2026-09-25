"""Trusted-only paired diagnostics, with equal weight per SKU and scene group.

Outputs aggregate counts only. This development set is not an independent test.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--profile', action='append', default=[], help='NAME=JSONL')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    labels = {row['sha256']: row for row in read(args.labels) if row['status'] == 'exact'}
    assert len(labels) == 54

    def predictions(path):
        rows = read(path)
        assert len(rows) == 103 and len({row['case_id'] for row in rows}) == 103
        by_sha = {}
        for row in rows:
            sha = row['query_sha256']
            if sha not in labels:
                continue
            outcome = row['http_status'] == 200 and row.get('result', {}).get('slug') == labels[sha]['exact_slug']
            if sha in by_sha:
                assert by_sha[sha] == outcome, 'Duplicate query has different outcomes; report separately'
            by_sha[sha] = outcome
        assert set(by_sha) == set(labels)
        return by_sha

    baseline = predictions(args.baseline)
    output = {'labels_sha256': hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
              'limits': ['Repeated development set, no independent accuracy claim.',
                         'Macro accuracy averages each group; all-correct is a stricter alternative.'],
              'profiles': {}}
    profiles = [('B', args.baseline)] + [(name, Path(path)) for name, path in
                                        (item.split('=', 1) for item in args.profile)]
    assert len(profiles) == len({name for name, _ in profiles})
    for name, path in profiles:
        pred = predictions(path)
        item = {'image_correct': sum(pred.values()), 'image_total': len(pred),
                'fixed': sum(pred[k] and not baseline[k] for k in pred),
                'broken': sum(baseline[k] and not pred[k] for k in pred),
                'predictions_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for field, key in [('exact_slug', 'sku'), ('scene_group', 'scene')]:
            groups = defaultdict(list)
            for sha, label in labels.items():
                assert label.get(field), 'Missing group'
                groups[label[field]].append(sha)
            item[key] = {
                'groups': len(groups),
                'macro_accuracy': sum(sum(pred[k] for k in group) / len(group)
                                      for group in groups.values()) / len(groups),
                'all_images_correct': sum(all(pred[k] for k in group) for group in groups.values()),
                'groups_with_fix': sum(any(pred[k] and not baseline[k] for k in group)
                                       for group in groups.values()),
                'groups_with_regression': sum(any(baseline[k] and not pred[k] for k in group)
                                              for group in groups.values())}
        output['profiles'][name] = item
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output))


if __name__ == '__main__':
    main()
