"""Export complete, gold-blind fresh-HTTP B→Roman submissions after 316 requests."""
import argparse
import collections
import hashlib
import json
import re
import statistics
from pathlib import Path


ROOT = Path('/Users/skif/ml-data/brutforce/night-20260925/roman')
PUBLIC = Path('/Users/skif/ml-data/brutforce/night-20260925/cpu/public-v2.json')


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values, pct):
    values = sorted(values)
    return values[min(len(values)-1, max(0, int((len(values)-1)*pct)))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--modes', nargs='+', choices=('roman5','roman20'), default=('roman5','roman20'))
    p.add_argument('--profile-tag',required=True)
    p.add_argument('--runtime-config',type=Path,required=True)
    p.add_argument('--server-source',type=Path,required=True)
    p.add_argument('--client-source',type=Path,required=True)
    args = p.parse_args()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',args.profile_tag):
        raise ValueError('Profile tag must be lower-case hyphenated')
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite existing HTTP export '+str(args.output))
    config=json.loads(args.runtime_config.read_text())
    if config['profile_tag']!=args.profile_tag:
        raise ValueError('Profile tag/runtime config mismatch')
    source_hashes=config['source_sha256']
    if hashlib.sha256(args.server_source.read_bytes()).hexdigest()!=source_hashes['online_server.py']:
        raise ValueError('Current server source hash mismatch')
    if hashlib.sha256(args.client_source.read_bytes()).hexdigest()!=source_hashes['online_client.py']:
        raise ValueError('Current client source hash mismatch')
    config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    expected = rows(args.root/'online-input-v1/requests.jsonl')
    observed = rows(args.source)
    assert len(expected) == len(observed) == 316
    assert len({r['case_id'] for r in observed}) == 316
    by_id = {r['case_id']: r for r in observed}
    for case in expected:
        result = by_id[case['case_id']]
        assert all(result[k] == case[k] for k in ('case_id', 'basket', 'track', 'query_sha256'))
        assert result['status'] in ('ok', 'timeout', 'error')
        assert result['elapsed_ms'] >= 0
        if result['status'] == 'ok':
            assert result['http_status'] == 200 and result['elapsed_ms'] <= 10000
            response = result['response']
            assert response['case_id'] == case['case_id']
            assert response['query_sha256'] == case['query_sha256']
            assert response['track'] == case['track']
            assert response['b_http_status'] == 200
            for mode in args.modes:
                rank = response[mode+'_ranked']
                assert len(rank) in (0,20) and len(rank) == len(set(rank))
                assert set(rank) == set(response['b_ranked'])
    ordered = [by_id[case['case_id']] for case in expected]
    server_modes = {r['response'].get('mode','twenty') for r in ordered if r['status'] == 'ok'}
    assert len(server_modes) == 1
    server_mode = server_modes.pop()
    if server_mode == 'five':
        assert tuple(args.modes) == ('roman5',)
    if config['server_mode']!=server_mode:
        raise ValueError('Runtime server mode mismatch')
    args.output.mkdir(parents=True)
    with (args.output/'paired-http.jsonl').open('w') as out:
        for result in ordered:
            out.write(json.dumps(result, ensure_ascii=False)+'\n')
    suite = json.loads(PUBLIC.read_text())
    modes = tuple(args.modes)
    ids = set()
    for mode in modes:
        for track in ('service', 'retrieval'):
            template = json.loads((args.root/'final'/f'{mode}-{track}.json').read_text())
            prefix = 'night-roman-'+args.profile_tag
            template['submission_id'] = f'{prefix}-{mode}-{track}-v2-20260925'
            assert template['submission_id'] not in ids
            ids.add(template['submission_id'])
            label = ('B OCR1280 quality variant' if config.get('ocr_input_max_side') else
                'B with 6 s deadline fallback' if config.get('b_skip_threshold_ms') else 'B')
            template['solution']['name'] = (
                f'Fresh HTTP {label} → Roman20 runtime-linear (client end-to-end timing)'
                if mode == 'roman20' else
                f'Fresh HTTP {label} → Roman5 runtime-linear (client end-to-end timing)'
                if server_mode == 'five' else
                f'Roman5 output from fresh {label} → Roman20 HTTP (timing includes Roman20)')
            template['solution']['version'] = f'roman-live-http-v1-{args.profile_tag}-{server_mode}-{mode}'
            template['solution']['config_hash'] = config_hash
            template['submitted_by'] = 'N4 fresh B→Roman HTTP experiment; strict 10 s client timeout'
            assert set(template['basket_ids']) == {b['basket_id'] for b in suite['baskets'] if b['track'] == track}
            for item in template['results']:
                client = by_id[item['case_id']]
                item['status'] = client['status']
                item['latency_ms'] = round(client['elapsed_ms'])
                if client['status'] != 'ok':
                    item['prediction'] = {}
                    continue
                response = client['response']
                ranking = response[mode+'_ranked']
                if track == 'retrieval':
                    # The retrieval scorer requires nonempty ranking on an OK response.
                    if not ranking:
                        item['status'] = 'error'
                        item['prediction'] = {}
                    else:
                        item['prediction'] = {'ranked_slugs': ranking}
                elif ranking:
                    item['prediction'] = {'slug': ranking[0]}
                else:
                    item['prediction'] = {'action': response['b_action'] or 'no_match'}
            (args.output/f'{mode}-{track}.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n')
        with (args.output/f'{mode}-organizer.jsonl').open('w') as out:
            for case in expected:
                if case['basket'] != 'organizer':
                    continue
                client = by_id[case['case_id']]
                ranking = client['response'][mode+'_ranked'] if client['status'] == 'ok' else []
                response = client['response'] if client['status'] == 'ok' else {}
                result = ({'action': 'match' if ranking else (response.get('b_action') or 'no_match'),
                          'slug': ranking[0] if ranking else None, 'ranked_slugs': ranking}
                          if client['status'] == 'ok' else {})
                out.write(json.dumps({'case_id': case['case_id'], 'query_sha256': case['query_sha256'],
                    'http_status': 200 if client['status'] == 'ok' else 0,
                    'raw_http_status':client['http_status'], 'client_status':client['status'],
                    'elapsed_ms':client['elapsed_ms'], 'result': result},ensure_ascii=False)+'\n')
    assert len(ids) == 2*len(modes)
    ok = [r for r in ordered if r['status'] == 'ok']
    cached = {r['case_id']:r for r in rows(args.root/'final/paired-predictions.jsonl')}
    assert len(cached) == 316
    parity = {'fresh_b_top20_equal':sum(r['response']['b_ranked'] == cached[r['case_id']]['b_ranked'] for r in ok)}
    for mode in modes:
        parity[mode+'_rank_equal'] = sum(r['response'][mode+'_ranked'] ==
            cached[r['case_id']][mode]['ranked_slugs'] for r in ok)
    summary = {'rows': len(ordered), 'status': dict(collections.Counter(r['status'] for r in ordered)),
        'by_basket': {basket: dict(collections.Counter(r['status'] for r in ordered if r['basket'] == basket))
                      for basket in ('frozen','organizer')},
        'latency_ms': {k: round(v,3) for k,v in {
            'p50': statistics.median(r['elapsed_ms'] for r in ordered),
            'p95': percentile([r['elapsed_ms'] for r in ordered],.95),
            'max': max(r['elapsed_ms'] for r in ordered)}.items()},
        'rank_parity_n': len(ok), 'rank_parity': parity,
        'http_source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'runtime_config_sha256': config_hash, 'profile_tag':args.profile_tag,
        'roman5_applied': sum('adapter5' in r['response'] for r in ok),
        'roman20_applied': sum('final20' in r['response'] for r in ok),
        'deadline_b_fallback_timely':sum(r['response'].get('status')=='deadline_b_fallback' for r in ok)}
    (args.output/'coverage-http.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
