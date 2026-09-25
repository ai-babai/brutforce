#!/usr/bin/env python3
"""Private aggregate scorer for organizer originals; run after gold-blind inference."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(items):
    statuses = collections.Counter(row['gold_status'] for row in items)
    gradeable = [row for row in items if row['gold_status'] in ('exact', 'out_of_catalog')]
    exact = [row for row in gradeable if row['gold_status'] == 'exact']
    absent = [row for row in gradeable if row['gold_status'] == 'out_of_catalog']
    return {
        'total': len(items), 'http_200': sum(row['http_status'] == 200 for row in items),
        'statuses': dict(statuses), 'gradeable': len(gradeable),
        'strict_correct': sum(row['correct'] for row in gradeable),
        'exact_top1': sum(row['correct'] for row in exact),
        'exact_top5': sum(row['top5'] for row in exact),
        'exact_top20': sum(row['top20'] for row in exact),
        'exact_total': len(exact),
        'absent_correct_no_match': sum(row['correct'] for row in absent),
        'absent_total': len(absent),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--predictions', type=Path, required=True)
    p.add_argument('--labels', type=Path, required=True)
    p.add_argument('--overlay', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--profile', required=True)
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = {row['case_id']: row for row in manifest['cases']}
    assert len(cases) == len(manifest['cases']) == 103
    assert len({row['sha256'] for row in manifest['cases']}) == 100
    labels = [json.loads(line) for line in args.labels.read_text().splitlines() if line.strip()]
    by_sha = {row['sha256']: row for row in labels}
    assert len(labels) == len(by_sha) == 100
    overlay = json.loads(args.overlay.read_text())
    changes = {row['sha256']: row for row in overlay['changes']}
    assert len(changes) == 1
    predictions = [json.loads(line) for line in args.predictions.read_text().splitlines() if line.strip()]
    assert len(predictions) == len({row['case_id'] for row in predictions}) == 103
    assert {row['case_id'] for row in predictions} == set(cases)
    assert len({row['query_sha256'] for row in predictions}) == 100
    scored = []
    for row in predictions:
        case = cases[row['case_id']]
        sha = case['sha256']
        assert row['query_sha256'] == sha
        label = by_sha[sha]
        result = row.get('result', {})
        status = 'out_of_catalog' if sha in changes else label['status']
        target = label.get('exact_slug') if status == 'exact' else None
        rank = result.get('ranked_slugs') or []
        correct = bool(row['http_status'] == 200 and (
            (status == 'exact' and result.get('slug') == target) or
            (status == 'out_of_catalog' and result.get('action') == 'no_match' and not rank)
        ))
        scored.append({'case_id': row['case_id'], 'sha256': sha,
                       'gold_status': status, 'http_status': row['http_status'],
                       'correct': correct,
                       'top5': bool(row['http_status'] == 200 and status == 'exact' and target in rank[:5]),
                       'top20': bool(row['http_status'] == 200 and status == 'exact' and target in rank[:20])})
    by_unique_sha = {}
    duplicate_outcome_disagreements = 0
    for row in scored:
        prior = by_unique_sha.setdefault(row['sha256'], row)
        if any(prior[key] != row[key] for key in ('correct', 'top5', 'top20', 'http_status')):
            duplicate_outcome_disagreements += 1
    unique = list(by_unique_sha.values())
    report = {
        'schema_version': 1, 'profile': args.profile,
        'manifest_sha256': file_hash(args.manifest),
        'predictions_sha256': file_hash(args.predictions),
        'labels_sha256': file_hash(args.labels),
        'overlay_sha256': file_hash(args.overlay),
        'request_level': summarize(scored),
        'unique_image_level': summarize(unique),
        'duplicate_outcome_disagreements': duplicate_outcome_disagreements,
        'limits': ['Internal corrected diagnostic labels, not organizer answer key.',
                   'Ambiguous and catalog-unresolved rows are excluded from strict accuracy.',
                   'The out-of-catalog decision uses the reviewed fixed organizer catalog snapshot.'],
    }
    with args.out.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    args.out.chmod(0o600)
    print(json.dumps({'request_level': report['request_level'],
                      'unique_image_level': report['unique_image_level']}))


if __name__ == '__main__':
    main()
