"""Export grayscale-label offline quality ablations with modeled stage times."""
import argparse
import hashlib
import json
from pathlib import Path

from fuse import VARIANTS


def read_rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--rows', type=Path, required=True)
    parser.add_argument('--v2-fused', type=Path, required=True)
    parser.add_argument('--gray-index', type=Path, required=True)
    parser.add_argument('--mode', required=True, choices=('gray', 'color_gray_equal_rrf60'))
    parser.add_argument('--variant', required=True, choices=VARIANTS)
    parser.add_argument('--track', required=True, choices=('service', 'retrieval'))
    parser.add_argument('--submission-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text())
    rows = {x['case_id']: x for x in read_rows(args.rows)}
    old = {x['case_id']: x for x in read_rows(args.v2_fused)}
    cases = [x for x in suite['cases'] if x['tracks'] == [args.track]]
    results = []
    for case in cases:
        cid = case['case_id']
        row = rows[cid]; prior = old[cid]
        if row['mode'] != args.mode or row['query_sha256'] != case['image_sha256']:
            raise ValueError('mode or query mismatch '+cid)
        if prior['query_sha256'] != case['image_sha256']:
            raise ValueError('v2 query mismatch '+cid)
        ranked = row['variants_top20'][args.variant]
        if args.track == 'service':
            pred = row['predictions'][args.variant]
            status = 'ok'
        else:
            pred = {'ranked_slugs': [x['slug'] for x in ranked]}
            status = 'ok' if ranked else 'error'
        latency = prior['variant_cached_stage_sum_ms'][args.variant]
        if 'label' in VARIANTS[args.variant]:
            if args.mode == 'gray':
                latency += row['gray_embedding_ms']-prior['timings_ms']['label_embedding_ms']
            else:
                latency += row['gray_embedding_ms']
        item = {'case_id': cid, 'status': status, 'latency_ms': max(0, round(latency))}
        if status == 'ok':
            item['prediction'] = pred
        results.append(item)
    sources = ('model.py', 'gray_label_ablation.py', 'gray_export_eval.py',
               'ranking.py', 'fuse.py', 'label_context_v2.py')
    digest = hashlib.sha256()
    for name in sources:
        digest.update((Path(__file__).parent/name).read_bytes())
    digest.update((args.gray_index/'gray-label.npz').read_bytes())
    baskets = sorted({b for c in cases for b in c['basket_ids']
                      if b.startswith('IMG-') == (args.track == 'service')})
    payload = {
        'submission_id': args.submission_id, 'suite_version': suite['version'],
        'suite_hash': suite['suite_hash'], 'track': args.track,
        'basket_ids': baskets,
        'solution': {
            'name': 'siglip2-gray-label-'+args.mode+'-'+args.variant,
            'version': 'v2-owlv2-offline-gray-label-20260925',
            'commit': None, 'config_hash': digest.hexdigest()[:16],
            'weights_version': 'OWLv2 pinned + SigLIP2 base224 pinned + PP-OCRv5 mobile',
            'catalog_version': suite['catalog_sha256'][:16],
        },
        'submitted_by': 'vision-retrieval-gray-ablation', 'results': results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'file': str(args.out), 'cases': len(results),
                      'errors': sum(x['status'] == 'error' for x in results),
                      'latency_kind': 'offline_cached_stage_sum_not_live_http'}))


if __name__ == '__main__':
    main()
