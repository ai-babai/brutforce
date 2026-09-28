"""Durable CPU-only HTTP bridge for the measured whole-encoder profile.

Uses whole_encoder_server.Pipeline without changing its ranking behavior.
No private evaluation labels are loaded by this process.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

CATALOG_VERSION = 'organizer-catalog-20260919'
INDEX_VERSION = 'so400m384-owlv2-v2-crops-reference-gated-20260925'
MODEL_VERSION = 'rtdetr-so400m-whole-only-v1'
PROFILE = 'whole-only'


class CPUPipeline:
    def __init__(self, catalog: Path, index_dir: Path, threads: int):
        import torch
        from whole_encoder_server import Pipeline

        catalog_info = json.loads(catalog.read_text())
        index_info = json.loads((index_dir / 'index-info.json').read_text())
        if catalog_info.get('version') != CATALOG_VERSION:
            raise ValueError('catalog version mismatch')
        if index_info.get('version') != INDEX_VERSION:
            raise ValueError('index version mismatch')
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        self.engine = Pipeline(catalog, index_dir, 'cpu')
        self.load_ms = self.engine.load_ms

    def predict(self, content: bytes, track: str) -> dict:
        raw = self.engine.predict(content, track)
        ranks = raw['branches_top20']['whole']
        ranked_slugs = list(dict.fromkeys(item['slug'] for item in ranks))[:20]
        if track == 'service' and raw.get('action'):
            ranked_slugs = []
        result = {
            'catalog_version': CATALOG_VERSION,
            'index_version': INDEX_VERSION,
            'model_version': MODEL_VERSION,
            'serving_profile': PROFILE,
            'ranked_slugs': ranked_slugs,
            'timings_ms': raw['timings_ms'],
            'image_sha256': raw['image_sha256'],
        }
        if track == 'service':
            if ranked_slugs:
                result['slug'] = ranked_slugs[0]
            else:
                result['action'] = raw.get('action', 'insufficient_information')
        return result


def make_handler(base_handler, pipeline, threads: int):
    class Handler(base_handler):
        inference_lock = threading.Lock()

        def do_POST(self):
            if not self.inference_lock.acquire(blocking=False):
                self.respond(503, {'error': 'vision inference busy'})
                return
            try:
                super().do_POST()
            finally:
                self.inference_lock.release()

        def respond(self, status, payload):
            try:
                super().respond(status, payload)
            except (BrokenPipeError, ConnectionResetError):
                # A timed-out client may disconnect while inference finishes.
                # Its result is discarded; the inference lock is still released.
                pass

        def do_GET(self):
            if self.path != '/healthz':
                self.send_error(404)
                return
            self.respond(200, {
                'status': 'ready',
                'catalog_version': CATALOG_VERSION,
                'index_version': INDEX_VERSION,
                'model_version': MODEL_VERSION,
                'serving_profile': PROFILE,
                'device': 'cpu',
                'threads': threads,
                'cold_load_ms': self.pipeline.load_ms,
                'busy': self.inference_lock.locked(),
                'max_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })

    Handler.pipeline = pipeline
    return Handler


def main() -> None:
    import server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8125)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    if args.threads < 1 or args.threads > 8:
        parser.error('--threads must be 1..8')
    if args.host != '127.0.0.1':
        parser.error('CPU test service must bind 127.0.0.1')
    os.environ.setdefault('OMP_NUM_THREADS', str(args.threads))
    os.environ.setdefault('MKL_NUM_THREADS', str(args.threads))
    pipeline = CPUPipeline(args.catalog, args.index_dir, args.threads)

    Handler = make_handler(server.Handler, pipeline, args.threads)
    print(json.dumps({'ready': True, 'model_version': MODEL_VERSION,
                      'profile': PROFILE, 'cold_load_ms': pipeline.load_ms,
                      'host': args.host, 'port': args.port}), flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
