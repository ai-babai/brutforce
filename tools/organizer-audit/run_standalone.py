"""Independent OCR + fixed catalog matcher on public organizer query manifests.

This runner has no access to labels or private eval records. It records every
paid attempt before writing predictions and resumes by image SHA + model.
"""
import argparse
import hashlib
import json
import signal
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'vision-baselines'
sys.path.insert(0, str(BASE))
import run as baseline
from matcher import Matcher

DATA = Path('/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit')
QUERY = DATA / 'queries-public.json'


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', choices=baseline.MODELS, required=True)
    ap.add_argument('--manifest', default=str(QUERY))
    ap.add_argument('--output-tag', default='standalone')
    ap.add_argument('--timeout', type=float, default=8)
    ap.add_argument('--max-combined', type=float, default=.70)
    ap.add_argument('--limit', type=int)
    args = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(args.manifest).read_text())['cases']
    if args.limit is not None:
        manifest = manifest[:args.limit]
    out = DATA / f'{args.model}-{args.output_tag}.jsonl'
    ledger = DATA / 'api-ledger.jsonl'
    existing = {(r['image_sha256'], r['model']) for r in rows(out)}
    matcher = Matcher()
    reserve = .008 if args.model == 'deepseek' else .015
    for case in manifest:
        path = Path(case['path'])
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != case['sha256']:
            raise RuntimeError(f'hash mismatch: {case["case_id"]}')
        if (sha, args.model) in existing:
            continue
        spent = sum(float(r.get('cost_usd') or r.get('reserved_usd') or 0) for r in rows(ledger))
        if spent + reserve > args.max_combined:
            print('budget_stop', args.model, case['case_id'], spent, flush=True)
            break
        start = time.monotonic()
        image = baseline.image_url(path, 1280)
        def _deadline(_signum, _frame):
            raise TimeoutError('hard total request deadline')
        prior = signal.signal(signal.SIGALRM, _deadline)
        signal.setitimer(signal.ITIMER_REAL, args.timeout + 2)
        try:
            status, reply, ms = baseline.call(args.model, image, baseline.PROMPT, args.timeout)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior)
        usage = reply.get('usage') or {}
        cost = usage.get('cost')
        baseline.append(ledger, {'at': baseline.utc(), 'case_id': case['case_id'], 'image_sha256': sha,
                                'model': args.model, 'prompt_version': 'vision-baselines-v1',
                                'status': status, 'cost_usd': cost, 'reserved_usd': reserve if cost is None else None,
                                'latency_ms': ms, 'provider_id': reply.get('id')})
        ocr = None
        if status == 'ok':
            try:
                ocr = baseline.parse_reply(reply)
            except Exception as exc:
                status = 'error'
                reply = {'parse_error': str(exc), 'raw_content': reply.get('choices', [{}])[0].get('message', {}).get('content', '')}
        ranked = matcher.rank(ocr) if ocr and ocr['action'] == 'wine' else []
        if ocr and ocr['action'] in ('no_wine', 'other_alcohol'):
            pred = {'action': 'no_match'}
        elif ocr and ocr['action'] == 'unreadable':
            pred = {'action': 'insufficient_information'}
        elif ranked and ranked[0]['score'] >= .12:
            pred = {'slug': ranked[0]['slug']}
        else:
            pred = {'action': 'insufficient_information'}
        existing.add((sha, args.model))
        baseline.append(out, {'case_id': case['case_id'], 'image_sha256': sha, 'track': 'service',
                             'model': args.model, 'status': status, 'prediction': pred if status == 'ok' else None,
                             'ocr': ocr, 'ranked': ranked, 'latency_ms': ms,
                             'total_latency_ms': round((time.monotonic()-start)*1000), 'api_cost_usd': cost,
                             'api_error': reply if status != 'ok' else None,
                             'source_set': case['source_set'], 'prompt_version': 'vision-baselines-v1',
                             'matcher_version': 'vision-baselines-v1', 'reuse': 'fresh_original_image'})
        print(args.model, case['case_id'], status, ms, cost, pred.get('slug', pred.get('action')), flush=True)


if __name__ == '__main__':
    main()
