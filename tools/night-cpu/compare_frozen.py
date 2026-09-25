#!/usr/bin/env python3
"""Private paired comparison by case, SKU and capture after inference is complete."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline-score', type=Path, required=True)
    p.add_argument('--candidate-score', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    baseline = json.loads(a.baseline_score.read_text())
    candidate = json.loads(a.candidate_score.read_text())
    manifest = json.loads(a.manifest.read_text())
    gold = json.loads(a.gold.read_text())
    assert baseline['track'] == candidate['track']
    assert manifest['suite_hash'] == gold['suite_hash']
    public = {x['case_id']: x for x in manifest['cases']}
    answers = {x['case_id']: x for x in gold['cases']}
    arows = {x['case_id']: x for x in baseline['cases'] if x['graded']}
    brows = {x['case_id']: x for x in candidate['cases'] if x['graded']}
    assert set(arows) == set(brows)

    def details(case_id):
        row = public[case_id]
        track = baseline['track']
        answer = answers[case_id][track]
        return {'case_id': case_id, 'scene_group_id': row.get('scene_group_id'),
                'origin_kind': row.get('origin_kind'),
                'expected_slug': answer.get('expected_slug'),
                'expected_action': answer.get('expected_action'),
                'baseline_status': arows[case_id]['status'],
                'candidate_status': brows[case_id]['status']}

    fixed = [details(k) for k in sorted(arows) if not arows[k]['correct'] and brows[k]['correct']]
    broken = [details(k) for k in sorted(arows) if arows[k]['correct'] and not brows[k]['correct']]
    result = {'track': baseline['track'], 'baseline': baseline['submission_id'],
              'candidate': candidate['submission_id'], 'fixed': fixed, 'broken': broken,
              'fixed_count': len(fixed), 'broken_count': len(broken),
              'fixed_distinct_skus': len({x['expected_slug'] for x in fixed if x['expected_slug']}),
              'broken_distinct_skus': len({x['expected_slug'] for x in broken if x['expected_slug']}),
              'fixed_capture_groups': len({x['scene_group_id'] for x in fixed}),
              'broken_capture_groups': len({x['scene_group_id'] for x in broken})}
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('fixed', 'broken')}))


if __name__ == '__main__':
    main()
