"""Cached-only candidate fusion and generic cultivar spelling experiment.

This script reads public catalog records and previously frozen model outputs.
It does not read gold, scorer reports, source-image mappings, or images; it
makes no model/API calls. Scores on the same suite are development results.
"""

import json
from collections import defaultdict

from matcher import Matcher, norm
from run import OUT, append


ALIASES = {
    'cabernet': 'kaberne', 'kaberne': 'kaberne',
    'sauvignon': 'sovinon', 'sovinon': 'sovinon', 'sovinjon': 'sovinon',
    'riesling': 'risling', 'risling': 'risling',
    'chardonnay': 'shardone', 'shardone': 'shardone',
    'pinot': 'pino', 'pino': 'pino', 'noir': 'nuar', 'nuar': 'nuar',
    'merlot': 'merlo', 'merlo': 'merlo',
    'muscat': 'muskat', 'muskat': 'muskat',
    'viognier': 'vione', 'vione': 'vione',
    'gewurztraminer': 'gevurstraminer', 'gevurstraminer': 'gevurstraminer',
}
VARIETY = {'kaberne', 'sovinon', 'risling', 'shardone', 'pino', 'nuar', 'merlo', 'muskat', 'vione', 'gevurstraminer'}


def cultivar_terms(s):
    return {ALIASES.get(word, word) for word in norm(s).split()} & VARIETY


def rerank(matcher, ocr):
    base = matcher.rank(ocr, limit=len(matcher.rows))
    query = cultivar_terms(' '.join((ocr.get('variety') or '', ocr.get('raw_text') or '')))
    if not query:
        return base[:20]
    rescored = []
    for row in base:
        catalog = matcher.rows[row['slug']]
        doc = cultivar_terms(' '.join((catalog['Название вина'], row['slug'])))
        overlap = len(query & doc) / len(query)
        new = dict(row)
        new['score'] = round(row['score'] + .12 * overlap, 4)
        rescored.append(new)
    rescored.sort(key=lambda x: (-x['score'], x['slug']))
    return rescored[:20]


def v2_record(source, matcher):
    row = dict(source)
    ocr = row.get('ocr') or {}
    if row['status'] == 'ok' and ocr.get('action') == 'wine':
        row['ranked'] = rerank(matcher, ocr)
        if row['track'] == 'retrieval':
            row['prediction'] = {'ranked_slugs': [x['slug'] for x in row['ranked']]}
        elif row['ranked'] and row['ranked'][0]['score'] >= .12:
            row['prediction'] = {'slug': row['ranked'][0]['slug']}
        else:
            row['prediction'] = {'action': 'insufficient_information'}
    row['variant'] = 'matcher-v2-generic-cultivar-aliases'
    row['source_model_record'] = source['case_id']
    row.pop('api_cost_usd', None)
    row.pop('api_usage', None)
    return row


def rrf_rows(deepseek, qwen, k=60):
    scores = defaultdict(float)
    for source in (deepseek, qwen):
        for rank, row in enumerate(source.get('ranked') or [], 1):
            scores[row['slug']] += 1 / (k + rank)
    return [{'slug': slug, 'score': round(score, 8)} for slug, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:20]]


def fused_record(d, q):
    if d['case_id'] != q['case_id'] or d['suite_hash'] != q['suite_hash'] or d['track'] != q['track']:
        raise ValueError('Frozen model records do not align')
    row = {'case_id': d['case_id'], 'track': d['track'], 'origin_kind': d['origin_kind'], 'basket_ids': d['basket_ids'],
           'suite_hash': d['suite_hash'], 'model': 'cached parallel simulation DeepSeek+Qwen RRF60',
           'variant': 'cached-parallel-rrf60-v1', 'latency_ms': max(d['latency_ms'], q['latency_ms']),
           'total_latency_ms': max(d['total_latency_ms'], q['total_latency_ms']), 'source_statuses': {'deepseek': d['status'], 'qwen': q['status']}}
    usable = [x for x in (d, q) if x['status'] == 'ok']
    if not usable:
        row.update(status='timeout' if 'timeout' in (d['status'], q['status']) else 'error', prediction=None, ranked=[])
        return row
    row['status'] = 'ok'
    row['ranked'] = rrf_rows(d if d['status'] == 'ok' else {}, q if q['status'] == 'ok' else {})
    if d['track'] == 'retrieval':
        row['prediction'] = {'ranked_slugs': [x['slug'] for x in row['ranked']]}
        return row
    # Conservative action gate: a no-match vote prevents a false wine match.
    actions = [(x.get('prediction') or {}).get('action') for x in usable]
    if 'no_match' in actions:
        row['prediction'] = {'action': 'no_match'}
    elif row['ranked']:
        row['prediction'] = {'slug': row['ranked'][0]['slug']}
    else:
        row['prediction'] = {'action': 'insufficient_information'}
    return row


def load(model):
    path = OUT / f'{model}-prompt-v1.jsonl'
    return {x['case_id']: x for x in map(json.loads, path.read_text().splitlines())}


def main():
    d, q = load('deepseek'), load('qwen')
    if set(d) != set(q) or len(d) != 213:
        raise SystemExit('Both frozen baseline outputs must cover the same 213 cases')
    matcher = Matcher()
    for name in ('deepseek-matcher-v2', 'qwen-matcher-v2', 'rrf60-cached-parallel-v1'):
        if (OUT / f'{name}.jsonl').exists():
            raise SystemExit(f'Refusing to overwrite: {name}.jsonl')
    for cid in sorted(d):
        append(OUT / 'deepseek-matcher-v2.jsonl', v2_record(d[cid], matcher))
        append(OUT / 'qwen-matcher-v2.jsonl', v2_record(q[cid], matcher))
        append(OUT / 'rrf60-cached-parallel-v1.jsonl', fused_record(d[cid], q[cid]))
    print('Wrote three cached-only 213-case variants. No model/API calls.')


if __name__ == '__main__':
    main()
