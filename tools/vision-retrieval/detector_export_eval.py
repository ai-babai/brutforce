"""Export full HTTP responses as frozen-suite submissions, without reading gold.

Only the ``all`` branch is the served HTTP prediction. Other branches are
quality ablations reconstructed from rankings returned by that same request;
their latency field conservatively copies the measured all-branch request.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fuse import VARIANTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--http-rows', type=Path, required=True)
    parser.add_argument('--variant', choices=VARIANTS, required=True)
    parser.add_argument('--track', choices=('service', 'retrieval'), required=True)
    parser.add_argument('--detector', required=True,
                        choices=('owlv2', 'yoloe26s', 'yoloe26s-strict', 'yolo26n',
                                 'yolo26n-geometric', 'rtdetr-r18', 'rtdetr-so400m'))
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--experiment-version', default='v2-index-detector-swap-20260925')
    parser.add_argument('--submission-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text())
    rows = [json.loads(x) for x in args.http_rows.read_text().splitlines() if x.strip()]
    by_id = {x['case_id']: x for x in rows}
    if len(by_id) != len(rows):
        raise ValueError('duplicate HTTP case IDs')
    cases = [c for c in suite['cases'] if c['tracks'] == [args.track]]
    results = []
    for case in cases:
        cid = case['case_id']
        if cid not in by_id:
            raise ValueError('missing case '+cid)
        row = by_id[cid]
        if row['variant'] != args.detector or row['track'] != args.track:
            raise ValueError('detector or track mismatch '+cid)
        if row['query_sha256'] != case['image_sha256']:
            raise ValueError('image hash mismatch '+cid)
        if row['http_status'] != 200:
            results.append({'case_id': cid, 'status': 'error',
                            'latency_ms': round(row['elapsed_ms'])})
            continue
        result = row['result']
        if result['image_sha256'] != case['image_sha256']:
            raise ValueError('response image hash mismatch '+cid)
        rank = result['variants_top20'][args.variant]
        if args.track == 'retrieval':
            prediction = {'ranked_slugs': [item['slug'] for item in rank]}
            status = 'ok' if rank else 'error'
        else:
            no_target = result['selection']['selected_box'] is None
            prediction = ({'action': 'no_match'} if no_target else
                          {'slug': rank[0]['slug']} if rank else
                          {'action': 'insufficient_information'})
            status = 'ok'
            if args.variant == 'all':
                served = {k: result[k] for k in ('slug', 'action') if k in result}
                if prediction != served:
                    raise ValueError('all-branch response differs from ranking '+cid)
        entry = {'case_id': cid, 'status': status,
                 'latency_ms': round(row['elapsed_ms'])}
        if status == 'ok':
            entry['prediction'] = prediction
        results.append(entry)
    basket_ids = sorted({b for case in cases for b in case['basket_ids']
                         if b.startswith('IMG-') == (args.track == 'service')})
    files = ('model.py', 'server.py', 'detector_variants.py', 'detector_server.py',
             'detector_run.py', 'detector_export_eval.py', 'ranking.py', 'fuse.py',
             'label_context_v2.py')
    if args.detector == 'rtdetr-so400m':
        files += ('detector_encoder_server.py', 'so400m_ablation.py')
    digest = hashlib.sha256()
    for name in files:
        digest.update((Path(__file__).parent/name).read_bytes())
    digest.update((args.index_dir/'index.npz').read_bytes())
    weights = ('YOLOE-26s-seg + MobileCLIP2' if args.detector.startswith('yoloe26s')
               else 'YOLO26n + OWLv2 label' if args.detector == 'yolo26n'
               else 'YOLO26n + geometric label' if args.detector == 'yolo26n-geometric'
               else 'RT-DETR-r18 + OWLv2 label + SigLIP2 SO400M/384 retrieval + Base224 wine classifier' if args.detector == 'rtdetr-so400m'
               else 'RT-DETR-r18 COCO bottle + OWLv2 label' if args.detector == 'rtdetr-r18'
               else 'OWLv2 pinned')
    submission = {
        'submission_id': args.submission_id,
        'suite_version': suite['version'], 'suite_hash': suite['suite_hash'],
        'track': args.track, 'basket_ids': basket_ids,
        'solution': {
            'name': args.detector+'-'+args.variant+(
                '-served-http' if args.variant == 'all' else '-quality-ablation'),
            'version': args.experiment_version, 'commit': None,
            'config_hash': digest.hexdigest()[:16],
            'weights_version': weights+' + SigLIP2 pinned + PP-OCRv5 mobile',
            'catalog_version': suite['catalog_sha256'][:16],
        },
        'submitted_by': 'vision-retrieval-detector-comparison',
        'results': results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(submission, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'submission': str(args.out), 'results': len(results),
                      'errors': sum(x['status'] == 'error' for x in results),
                      'latency_note': 'measured full all-branch HTTP latency, copied to quality ablations'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
