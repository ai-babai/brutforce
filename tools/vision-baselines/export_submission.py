"""Export recorded predictions to the public eval submission contract.

This reads neither private gold nor scoring feedback. It never invokes a model.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from matcher import DATA
from run import MODELS, OUT


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=[*MODELS, 'paddle', 'deepseek-v2', 'qwen-v2', 'rrf60'], required=True)
    p.add_argument('--track', choices=['service', 'retrieval'], required=True)
    p.add_argument('--case-id', action='append')
    p.add_argument('--name', required=True)
    args = p.parse_args()
    suite = json.loads((DATA / 'baskets/v1.json').read_text())
    wanted = set(args.case_id or [])
    sources = {'paddle': 'paddle.jsonl', 'deepseek-v2': 'deepseek-matcher-v2.jsonl', 'qwen-v2': 'qwen-matcher-v2.jsonl', 'rrf60': 'rrf60-cached-parallel-v1.jsonl'}
    source = OUT / sources.get(args.model, f'{args.model}-prompt-v1.jsonl')
    records = [json.loads(line) for line in source.read_text().splitlines()]
    records = [r for r in records if r['track'] == args.track and (not wanted or r['case_id'] in wanted)]
    if any(r.get('suite_hash') != suite['suite_hash'] for r in records):
        raise SystemExit('A recorded result has a different sealed suite hash')
    if wanted - {r['case_id'] for r in records}:
        raise SystemExit('A requested case has no recorded prediction')
    by_id = {r['case_id']: r for r in records}
    cases = [c for c in suite['cases'] if c['case_id'] in by_id]
    baskets = sorted({b for c in cases for b in c['basket_ids'] if b.startswith('IMG-') == (args.track == 'service')})
    results = []
    overdue = []
    no_candidate = []
    for case in cases:
        r = by_id[case['case_id']]
        total_ms = r.get('total_latency_ms', r['latency_ms'])
        status = 'timeout' if total_ms > 10000 else r['status']
        if status == 'timeout' and r['status'] != 'timeout':
            overdue.append({'case_id': r['case_id'], 'raw_status': r['status'], 'api_latency_ms': r['latency_ms'], 'total_latency_ms': total_ms, 'reason': 'client_total_over_10s'})
        if args.track == 'retrieval' and status == 'ok' and not (r.get('prediction') or {}).get('ranked_slugs'):
            status = 'error'
            no_candidate.append({'case_id': r['case_id'], 'raw_status': r['status'], 'reason': 'ocr_or_matcher_produced_no_catalog_candidate'})
        item = {'case_id': r['case_id'], 'status': status, 'latency_ms': total_ms}
        if status == 'ok':
            item['prediction'] = r['prediction']
        results.append(item)
    if args.model == 'paddle':
        source_files = ('paddle_remote.py', 'postprocess_paddle.py', 'matcher.py')
    elif args.model in ('deepseek-v2', 'qwen-v2', 'rrf60'):
        source_files = ('offline_variants.py', 'run.py', 'matcher.py')
    else:
        source_files = ('run.py', 'matcher.py')
    code = b''.join((Path(__file__).parent / n).read_bytes() for n in source_files)
    weights_map = {**MODELS, 'paddle': 'PaddleOCR 3.7.0 PP-OCRv5 eslav mobile CPU', 'deepseek-v2': MODELS['deepseek'], 'qwen-v2': MODELS['qwen'], 'rrf60': MODELS['deepseek'] + ' + ' + MODELS['qwen']}
    weights = weights_map[args.model]
    solution_name = 'cached-parallel-rrf60-deepseek-qwen' if args.model == 'rrf60' else f'{args.model}-ocr-lexical'
    submission = {'submission_id': args.name, 'suite_version': suite['version'], 'suite_hash': suite['suite_hash'], 'track': args.track, 'basket_ids': baskets,
                  'solution': {'name': solution_name, 'version': '0.1', 'commit': None, 'config_hash': hashlib.sha256(code).hexdigest()[:16], 'weights_version': weights, 'catalog_version': suite['catalog_sha256'][:16]},
                  'submitted_by': 'vision-baselines', 'results': results}
    path = OUT / f'{args.name}.submission.json'
    path.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + '\n')
    if overdue:
        audit = OUT / f'{args.name}.deadline-adjustments.json'
        audit.write_text(json.dumps(overdue, ensure_ascii=False, indent=2) + '\n')
    if no_candidate:
        audit = OUT / f'{args.name}.no-candidate.json'
        audit.write_text(json.dumps(no_candidate, ensure_ascii=False, indent=2) + '\n')
    print(path, len(results), len(baskets), 'overdue_as_timeout', len(overdue), 'no_candidate_as_error', len(no_candidate))


if __name__ == '__main__':
    main()
