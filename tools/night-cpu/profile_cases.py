#!/usr/bin/env python3
"""Gold-blind stage profiler for an isolated whole-only CPU runtime."""
import argparse
import hashlib
import json
import os
import resource
import time
import importlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ids', nargs='+', required=True)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--pipeline', default='whole_encoder_server')
    args = parser.parse_args()
    os.environ.setdefault('OMP_NUM_THREADS', str(args.threads))
    os.environ.setdefault('MKL_NUM_THREADS', str(args.threads))
    import torch
    Pipeline = importlib.import_module(args.pipeline).Pipeline
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    load_start = time.perf_counter()
    engine = Pipeline(args.catalog, args.index_dir, 'cpu')
    print(json.dumps({'event': 'ready', 'cold_load_ms': round((time.perf_counter()-load_start)*1000),
                      'threads': args.threads, 'pid': os.getpid()}), flush=True)
    cases = {c['case_id']: c for c in json.loads(args.manifest.read_text())['cases']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w') as output:
        for cid in args.ids:
            case = cases[cid]
            image = args.image_root / case['image_path']
            content = image.read_bytes()
            assert hashlib.sha256(content).hexdigest() == case['image_sha256']
            started = time.perf_counter()
            try:
                raw = engine.predict(content, case['tracks'][0])
                status = 'ok'
            except Exception as exc:
                raw = {'error': repr(exc)}
                status = 'error'
            row = {'case_id': cid, 'status': status,
                   'elapsed_ms': round((time.perf_counter()-started)*1000),
                   'image_bytes': len(content), 'result': raw,
                   'max_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            output.write(json.dumps(row, ensure_ascii=False)+'\n')
            output.flush()
            print(json.dumps({'case_id': cid, 'elapsed_ms': row['elapsed_ms'],
                              'timings_ms': raw.get('timings_ms'),
                              'selection_reason': raw.get('selection', {}).get('selection_reason'),
                              'label_selection': raw.get('label_selection'),
                              'max_rss_kb': row['max_rss_kb']}), flush=True)


if __name__ == '__main__':
    main()
