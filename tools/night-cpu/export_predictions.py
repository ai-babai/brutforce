#!/usr/bin/env python3
"""Export complete frozen-v2 submissions from gold-blind CPU HTTP rows."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--rows', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--id-prefix', required=True)
    p.add_argument('--branch', choices=['served', 'whole', 'label', 'ocr'], default='served')
    p.add_argument('--solution-name')
    args = p.parse_args()
    suite = json.loads(args.manifest.read_text())
    assert suite['version'] == 'v2'
    cases = {c['case_id']: c for c in suite['cases']}
    rows = [json.loads(line) for line in args.rows.read_text().splitlines() if line.strip()]
    by_id = {r['case_id']: r for r in rows}
    assert len(by_id) == len(rows) == len(cases), 'incomplete or duplicate HTTP rows'
    assert set(by_id) == set(cases), 'missing or unknown HTTP case'
    config_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for track in ('service', 'retrieval'):
        branch_scope = {'served': 'served output; measured full HTTP latency',
                        'whole': 'whole-only output; measured same full HTTP latency',
                        'label': 'label-only output; measured same full HTTP latency',
                        'ocr': 'OCR-only output; measured same full HTTP latency'}[args.branch]
        output = {'submission_id': args.id_prefix + '-' + args.branch + '-' + track,
                  'suite_version': suite['version'], 'suite_hash': suite['suite_hash'],
                  'track': track,
                  'basket_ids': [b['basket_id'] for b in suite['baskets'] if b['track'] == track],
                  'solution': {'name': (args.solution_name or 'Sigma isolated CPU ' + args.id_prefix)
                                      + ' · ' + branch_scope,
                               'version': args.id_prefix + '-' + args.branch,
                               'commit': None, 'config_hash': config_hash,
                               'weights_version': args.id_prefix,
                               'catalog_version': 'organizer-catalog-20260919'},
                  'submitted_by': 'isolated CPU benchmark', 'results': []}
        for case in suite['cases']:
            if case['tracks'] != [track]:
                continue
            row = by_id[case['case_id']]
            assert row['query_sha256'] == case['image_sha256']
            result = row.get('result', {})
            prediction = {}
            status = 'error'
            if row['http_status'] == 200 and row['elapsed_ms'] <= 10000:
                assert result['image_sha256'] == case['image_sha256']
                assert result['catalog_version'] == 'organizer-catalog-20260919'
                if args.branch == 'served':
                    ranking = result.get('ranked_slugs', [])
                    action = result.get('action')
                else:
                    ranking = [x['slug'] for x in result['branches_top20'][args.branch]]
                    action = result.get('action') or 'insufficient_information'
                if track == 'service' and ranking:
                    prediction, status = {'slug': ranking[0]}, 'ok'
                elif track == 'service' and action in ('no_match', 'insufficient_information'):
                    prediction, status = {'action': action}, 'ok'
                elif track == 'retrieval' and ranking:
                    prediction, status = {'ranked_slugs': ranking[:20]}, 'ok'
            elif row['elapsed_ms'] > 10000 or 'timed out' in str(result.get('error', '')).lower():
                status = 'timeout'
            output['results'].append({'case_id': case['case_id'], 'status': status,
                                      'prediction': prediction, 'latency_ms': round(row['elapsed_ms'])})
        path = args.out_dir / (output['submission_id'] + '.json')
        with path.open('x') as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        path.chmod(0o600)
        print(json.dumps({'track': track, 'results': len(output['results']), 'path': str(path)}))


if __name__ == '__main__':
    main()
