#!/usr/bin/env python3
"""Local-only scorer: never import this into an inference process."""
import argparse
import collections
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--submission', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    gold = json.loads(a.gold.read_text())
    suite = json.loads(a.manifest.read_text())
    sub = json.loads(a.submission.read_text())
    assert gold['version'] == suite['version'] == sub['suite_version'] == 'v2'
    assert gold['suite_hash'] == suite['suite_hash'] == sub['suite_hash']
    assert sub['track'] in ('service', 'retrieval')
    expected_baskets = {b['basket_id'] for b in suite['baskets'] if b['track'] == sub['track']}
    assert set(sub['basket_ids']) == expected_baskets
    assert len(sub['basket_ids']) == len(expected_baskets)
    expected_cases = {c['case_id'] for c in suite['cases'] if c['tracks'] == [sub['track']]}
    assert len(expected_cases) == (151 if sub['track'] == 'service' else 62)
    lookup = {c['case_id']: c for c in gold['cases']}
    assert len(lookup) == len(gold['cases']) == len(suite['cases']) == 213
    assert set(lookup) == {c['case_id'] for c in suite['cases']}
    assert len(sub['results']) == len(expected_cases)
    assert {r['case_id'] for r in sub['results']} == expected_cases
    rows = []
    for r in sub['results']:
        g = lookup[r['case_id']]
        assert r['status'] in ('ok', 'error', 'timeout')
        assert r['latency_ms'] >= 0
        if r['status'] == 'ok':
            pred = r['prediction']
            if sub['track'] == 'service':
                action = pred.get('action') or ('match' if pred.get('slug') else '')
                assert action in ('match', 'no_match', 'insufficient_information')
                assert (action == 'match') == bool(pred.get('slug'))
            else:
                ranking = pred.get('ranked_slugs', [])
                assert ranking and len(ranking) == len(set(ranking))
        if not g['verified'] or sub['track'] not in g:
            rows.append({'case_id': r['case_id'], 'graded': False, 'status': r['status']})
            continue
        answer = g[sub['track']]
        pred = r['prediction'] if r['status'] == 'ok' else {}
        if sub['track'] == 'service':
            expected_action = answer.get('expected_action') or ('match' if answer.get('expected_slug') else '')
            assert expected_action in ('match', 'no_match', 'insufficient_information')
            action = pred.get('action') or ('match' if pred.get('slug') else '')
            correct = bool(r['status'] == 'ok' and action == expected_action and
                           (action != 'match' or pred.get('slug') == answer.get('expected_slug')))
            rows.append({'case_id': r['case_id'], 'graded': True, 'status': r['status'],
                         'correct': bool(correct)})
        else:
            ranking = pred.get('ranked_slugs', [])
            expected = answer['expected_slug']
            rank = ranking.index(expected)+1 if r['status'] == 'ok' and expected in ranking else None
            rows.append({'case_id': r['case_id'], 'graded': True, 'status': r['status'],
                         'rank': rank, 'correct': rank == 1})
    graded = [r for r in rows if r['graded']]
    report = {'submission_id': sub['submission_id'], 'track': sub['track'],
              'submitted': len(rows), 'graded': len(graded),
              'ungraded': len(rows)-len(graded),
              'status_all': dict(collections.Counter(r['status'] for r in rows)),
              'top1_or_pass': sum(r['correct'] for r in graded), 'cases': rows}
    if sub['track'] == 'retrieval':
        report.update({'top5': sum(r['rank'] is not None and r['rank'] <= 5 for r in graded),
                       'top20': sum(r['rank'] is not None and r['rank'] <= 20 for r in graded),
                       'mrr': sum(1/r['rank'] for r in graded if r['rank']) / len(graded)})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}))


if __name__ == '__main__':
    main()
