"""Run label-free detector and full-HTTP comparisons on public manifests."""
import argparse
import hashlib
import json
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path

from model import Vision, load_image
from detector_variants import make_vision


def cases_from_manifest(path):
    raw = path.read_bytes()
    obj = json.loads(raw)
    cases = []
    for case in obj['cases']:
        if 'tracks' in case:
            if len(case['tracks']) != 1:
                raise ValueError('expected one track per suite case')
            track = case['tracks'][0]
        else:
            track = case['track']
        cases.append({
            'case_id': case['case_id'], 'track': track,
            'path': case.get('image_path', case.get('path')),
            'sha256': case.get('image_sha256', case.get('sha256')),
        })
    return hashlib.sha256(raw).hexdigest(), cases


def image_path(root, case):
    rel = Path(case['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('unsafe image path')
    return root / rel


def append(path, row):
    with path.open('a') as handle:
        handle.write(json.dumps(row, ensure_ascii=False)+'\n')
        handle.flush()


def detection(args, manifest_hash, cases, existing):
    model = Vision(args.device) if args.variant == 'owlv2' else make_vision(args.variant, args.device)
    for case in cases:
        if case['case_id'] in existing or case['track'] != 'service':
            continue
        path = image_path(args.image_root, case)
        image = load_image(path, case['sha256'])
        started = time.perf_counter()
        target, selection = model.select_service(image)
        label = None
        if target is None and selection['selection_reason'] == 'no_bottle_detected':
            _, label = model.label_region(image)
            if (label['source'].startswith(('owlv2', 'yoloe26s'))
                    and label['score'] >= .15):
                selection['selected_box'] = label['box']
                selection['selection_reason'] = 'standalone_label_no_bottle'
        row = {
            'case_id': case['case_id'], 'track': case['track'],
            'query_sha256': case['sha256'], 'manifest_sha256': manifest_hash,
            'variant': args.variant, 'run_id': args.run_id,
            'phase': args.phase, 'device': args.device, 'selection': selection,
            'standalone_label': label,
            'elapsed_ms': round((time.perf_counter()-started)*1000),
        }
        append(args.out, row)
        print(json.dumps({'case_id': case['case_id'],
                          'selection_reason': selection['selection_reason'],
                          'elapsed_ms': row['elapsed_ms']}), flush=True)


def full_http(args, manifest_hash, cases, existing):
    parts = urlsplit(args.url)
    health_url = urlunsplit((parts.scheme, parts.netloc, '/healthz', '', ''))
    with urllib.request.urlopen(health_url, timeout=10) as response:
        health = json.load(response)
    if health.get('status') != 'ready':
        raise ValueError('server not ready')
    for case in cases:
        if case['case_id'] in existing:
            continue
        path = image_path(args.image_root, case)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != case['sha256']:
            raise ValueError('image hash mismatch: '+case['case_id'])
        req = urllib.request.Request(
            args.url+'?track='+case['track'], data=raw,
            headers={'Content-Type': 'application/octet-stream'}, method='POST',
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as response:
                status = response.status
                result = json.load(response)
        except Exception as exc:
            status = None
            result = {'error': type(exc).__name__+': '+str(exc)[:250]}
        elapsed = round((time.perf_counter()-started)*1000, 2)
        if status == 200 and result.get('image_sha256') != case['sha256']:
            raise ValueError('server image hash mismatch: '+case['case_id'])
        row = {
            'case_id': case['case_id'], 'track': case['track'],
            'query_sha256': case['sha256'], 'manifest_sha256': manifest_hash,
            'variant': args.variant, 'run_id': args.run_id,
            'phase': args.phase, 'device': args.device,
            'url': args.url, 'http_status': status,
            'elapsed_ms': elapsed, 'result': result,
        }
        append(args.out, row)
        print(json.dumps({'case_id': case['case_id'], 'http_status': status,
                          'elapsed_ms': elapsed,
                          'action': result.get('action'),
                          'slug': result.get('slug')}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True, choices=('detect', 'full-http'))
    parser.add_argument('--variant', required=True,
                        choices=('owlv2', 'yoloe26s', 'yoloe26s-strict', 'yolo26n',
                                 'yolo26n-geometric', 'rtdetr-r18', 'rtdetr-so400m'))
    parser.add_argument('--run-id', required=True,
                        help='Unique identity including hardware, source and index version')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--url', default='http://127.0.0.1:8080/v1/eval/predict')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    manifest_hash, cases = cases_from_manifest(args.manifest)
    if args.limit:
        cases = cases[:args.limit]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    prior = [json.loads(x) for x in args.out.read_text().splitlines()] if args.out.exists() else []
    if any(x['variant'] != args.variant or x['manifest_sha256'] != manifest_hash
           or x['run_id'] != args.run_id or x['phase'] != args.phase
           or x['device'] != args.device
           or (args.phase == 'full-http' and x['url'] != args.url) for x in prior):
        raise ValueError('existing output has different model or manifest')
    existing = {x['case_id'] for x in prior}
    if args.phase == 'detect':
        if args.variant == 'rtdetr-so400m':
            parser.error('rtdetr-so400m is a full-HTTP composition only')
        detection(args, manifest_hash, cases, existing)
    else:
        full_http(args, manifest_hash, cases, existing)


if __name__ == '__main__':
    main()
