"""Serve a detector variant through the unchanged v2 pipeline and HTTP API."""
import argparse
import json
from http.server import HTTPServer
from pathlib import Path

import server
from detector_variants import make_vision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', required=True,
                        choices=('yoloe26s', 'yoloe26s-strict', 'yolo26n',
                                 'yolo26n-geometric', 'rtdetr-r18'))
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--ocr-threads', type=int, default=2)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server.Vision = lambda device: make_vision(args.variant, device)
    pipeline = server.Pipeline(args.catalog, args.index_dir, args.device,
                               args.ocr_threads, label_context=True)
    server.Handler.pipeline = pipeline
    print(json.dumps({'ready': True, 'variant': args.variant,
                      'cold_load_ms': pipeline.load_ms, 'device': pipeline.device,
                      'gpu_name': pipeline.gpu_name}), flush=True)
    HTTPServer((args.host, args.port), server.Handler).serve_forever()


if __name__ == '__main__':
    main()
