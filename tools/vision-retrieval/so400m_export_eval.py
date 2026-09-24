"""Export controlled SigLIP2 encoder quality ablations with modeled stage times."""
import argparse
import hashlib
import json
from pathlib import Path

from fuse import VARIANTS


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--base-fused', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--model', choices=('so400m384', 'base224'), default='so400m384')
    parser.add_argument('--detector', choices=('owlv2', 'rtdetr-r18'), default='owlv2')
    parser.add_argument('--gate-version', choices=('v1', 'v2'), default='v2')
    parser.add_argument('--variant', choices=VARIANTS, required=True)
    parser.add_argument('--track', choices=('service', 'retrieval'), required=True)
    parser.add_argument('--submission-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text())
    new = {x['case_id']: x for x in rows(args.results)}
    expected_model = ('google/siglip2-so400m-patch16-384' if args.model == 'so400m384'
                      else 'google/siglip2-base-patch16-224')
    if any(not x.get('model', x.get('encoder', '')).startswith(expected_model+'@')
           for x in new.values()):
        raise ValueError('query encoder does not match requested model')
    base = {x['case_id']: x for x in rows(args.base_fused)}
    cases = [x for x in suite['cases'] if x['tracks'] == [args.track]]
    output = []
    for case in cases:
        cid = case['case_id']; result = new[cid]; old = base[cid]
        if result['query_sha256'] != case['image_sha256'] or old['query_sha256'] != case['image_sha256']:
            raise ValueError('query hash mismatch '+cid)
        ranked = result['variants_top20'][args.variant]
        if args.track == 'service':
            prediction = result['predictions'][args.variant]
            status = 'ok'
        else:
            prediction = {'ranked_slugs': [x['slug'] for x in ranked]}
            status = 'ok' if ranked else 'error'
        if args.detector == 'rtdetr-r18':
            if result.get('detector') != 'rtdetr-r18':
                raise ValueError('detector mismatch '+cid)
            # Source HTTP includes the original full RT/OCR request. Adding
            # the new embeddings is a conservative offline estimate only.
            latency = result['source_http_elapsed_ms']
            if 'whole' in VARIANTS[args.variant]:
                latency += result['whole_embedding_ms']
            if 'label' in VARIANTS[args.variant]:
                latency += result['label_embedding_ms']
        else:
            latency = old['variant_cached_stage_sum_ms'][args.variant]
            if 'whole' in VARIANTS[args.variant]:
                latency += result['whole_embedding_ms']-old['timings_ms']['whole_embedding_ms']
            if 'label' in VARIANTS[args.variant]:
                latency += result['label_embedding_ms']-old['timings_ms']['label_embedding_ms']
        row = {'case_id': cid, 'status': status, 'latency_ms': max(0, round(latency))}
        if status == 'ok':
            row['prediction'] = prediction
        output.append(row)
    digest = hashlib.sha256()
    names = ('so400m_ablation.py', 'so400m_export_eval.py', 'ranking.py',
             'fuse.py', 'label_context_v2.py')
    if args.detector == 'rtdetr-r18':
        names += ('encoder_detector_composition.py',)
    for name in names:
        digest.update((Path(__file__).parent/name).read_bytes())
    digest.update((args.index_dir/'index.npz').read_bytes())
    baskets = sorted({b for case in cases for b in case['basket_ids']
                      if b.startswith('IMG-') == (args.track == 'service')})
    payload = {
        'submission_id': args.submission_id,
        'suite_version': suite['version'], 'suite_hash': suite['suite_hash'],
        'track': args.track, 'basket_ids': baskets,
        'solution': {
            'name': args.detector+'-siglip2-'+args.model+'-reference-gated-'+args.gate_version+'-'+args.variant,
            'version': args.detector+'-v2-crops-'+args.model+'-reference-gated-'+args.gate_version+'-offline-20260925',
            'commit': None, 'config_hash': digest.hexdigest()[:16],
            'weights_version': args.detector+' + OWLv2 label + SigLIP2 '+args.model+' pinned + PP-OCRv5 mobile',
            'catalog_version': suite['catalog_sha256'][:16],
        },
        'submitted_by': 'vision-retrieval-encoder-ablation', 'results': output,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'file': str(args.out), 'cases': len(output),
                      'errors': sum(x['status'] == 'error' for x in output),
                      'latency_kind': 'offline_conservative_estimate_not_live_http'}))


if __name__ == '__main__':
    main()
