"""Apply the shared lexical matcher to independent PaddleOCR raw output."""

import json
from pathlib import Path

from matcher import DATA, Matcher
from run import OUT, append


def main():
    raw = OUT / 'paddle-ocr.jsonl'
    target = OUT / 'paddle.jsonl'
    suite = json.loads((DATA / 'baskets/v1.json').read_text())
    cases = {c['case_id']: c for c in suite['cases']}
    matcher = Matcher()
    existing = {json.loads(line)['case_id'] for line in target.read_text().splitlines()} if target.exists() else set()
    for line in raw.read_text().splitlines():
        x = json.loads(line)
        cid = x['case_id']
        if cid in existing:
            continue
        case = cases[cid]
        text = '\n'.join(s for s, confidence in zip(x['texts'], x['scores']) if confidence >= .35)
        obj = {'action': 'wine' if text else 'unreadable', 'raw_text': text, 'producer': '', 'wine_name': '', 'variety': '', 'vintage': ''}
        ranked = matcher.rank(obj) if text else []
        if case['tracks'][0] == 'retrieval':
            pred = {'ranked_slugs': [r['slug'] for r in ranked]}
        elif ranked and ranked[0]['score'] >= .12:
            pred = {'slug': ranked[0]['slug']}
        else:
            pred = {'action': 'insufficient_information'}
        status = x['status']
        row = {'case_id': cid, 'track': x['track'], 'origin_kind': case['origin_kind'], 'basket_ids': case['basket_ids'], 'status': status, 'prediction': pred if status == 'ok' else None, 'ocr': obj, 'ranked': ranked, 'latency_ms': x['latency_ms'], 'total_latency_ms': x['latency_ms'], 'model': 'PaddleOCR 3.7.0 PP-OCRv5 ru mobile detection on Sigma CPU', 'suite_hash': suite['suite_hash'], 'selection': x['selection'], 'error': x['error']}
        append(target, row)
        print(cid, status, row['latency_ms'], ranked[0]['slug'] if ranked else '-', flush=True)


if __name__ == '__main__':
    main()
