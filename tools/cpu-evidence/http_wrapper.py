"""Low-memory CPU evidence bridge: one existing ORT6 backend, optional target OCR."""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from processor import EvidenceProcessor


class Bridge:
    def __init__(self, backend: str, cards: Path, catalog: Path, ocr_url: str, ocr_timeout: float):
        info = json.loads(catalog.read_text())
        if info['version'] != 'organizer-catalog-20260919':
            raise ValueError('catalog version mismatch')
        slugs = [item['slug'] for item in info['references']]
        self.evidence = EvidenceProcessor(json.loads(cards.read_text()), slugs, ocr_url, ocr_timeout)
        self.backend = backend.rstrip('/')
        self.catalog_version = info['version']

    def health(self):
        with urllib.request.urlopen(self.backend + '/healthz', timeout=2) as response:
            payload = json.load(response)
        if payload.get('status') != 'ready' or payload.get('catalog_version') != self.catalog_version:
            raise ValueError('backend catalog/health mismatch')
        return payload

    def predict(self, image: bytes, track: str):
        request = urllib.request.Request(self.backend + '/v1/eval/predict?track=' + track,
            data=image, method='POST', headers={'Content-Type': 'application/octet-stream',
                                                 'X-ML083-Diagnostic': 'target-v1'})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=9) as response:
            result = json.load(response)
        backend_ms = round((time.perf_counter()-started)*1000)
        selection = result.pop('target_selection', None)
        if not isinstance(selection, dict) or not isinstance(selection.get('whole_top20'), list):
            raise ValueError('backend did not expose opt-in target metadata')
        ranks = selection['whole_top20']
        if (result.get('image_sha256') != hashlib.sha256(image).hexdigest() or
                result.get('catalog_version') != self.catalog_version or
                result.get('model_version') != 'rtdetr-so400m-whole-only-v1-onnx640' or
                result.get('ranked_slugs') != [item['slug'] for item in ranks]):
            raise ValueError('backend SHA/version/whole-rank mismatch')
        ranks, evidence, evidence_ms = self.evidence.rerank(
            image, selection, ranks, track, backend_ms)
        result['ranked_slugs'] = [item['slug'] for item in ranks]
        if track == 'service' and result['ranked_slugs']:
            result['slug'] = result['ranked_slugs'][0]
        result['model_version'] += '-evidence-v1'
        result['serving_profile'] += '-evidence-v1'
        result['selection_reason'] = selection['selection_reason']
        result['branches_top20'] = {'whole': selection['whole_top20']}
        result['evidence'] = evidence
        result['ocr_used'] = evidence['ocr_timeout_ms'] is not None
        result['ocr_text'] = '\n'.join(evidence['ocr_texts'])
        result['ocr_error'] = evidence['ocr_error']
        result['timings_ms']['backend_wall_ms'] = backend_ms
        result['timings_ms']['evidence_ms'] = evidence_ms
        result['timings_ms']['ocr_ms'] = evidence_ms if result['ocr_used'] else 0
        result['timings_ms']['total_ms'] = backend_ms + evidence_ms
        return result


def make_handler(bridge: Bridge):
    class Handler(BaseHTTPRequestHandler):
        inference_lock = threading.Lock()

        def respond(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path != '/healthz':
                self.respond(404, {'error': 'unknown route'})
                return
            try:
                health = bridge.health()
                self.respond(200, {'status': 'ready', 'busy': self.inference_lock.locked() or
                    health.get('busy', False), 'catalog_version': bridge.catalog_version,
                    'index_version': health['index_version'], 'device': 'cpu',
                    'model_version': health['model_version'] + '-evidence-v1',
                    'serving_profile': health['serving_profile'] + '-evidence-v1'})
            except Exception as exc:
                self.respond(503, {'error': type(exc).__name__ + ': ' + str(exc)[:200]})

        def do_POST(self):
            parsed = urlsplit(self.path)
            if parsed.path != '/v1/eval/predict':
                self.respond(404, {'error': 'unknown route'})
                return
            if not self.inference_lock.acquire(blocking=False):
                self.respond(503, {'error': 'vision inference busy'})
                return
            try:
                track = parse_qs(parsed.query).get('track', ['service'])[0]
                if track not in ('service', 'retrieval'):
                    raise ValueError('invalid track')
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 30_000_000:
                    raise ValueError('image body size')
                body = self.rfile.read(length)
                content_type = self.headers.get('Content-Type', '')
                if content_type.startswith('multipart/form-data'):
                    mime = b'Content-Type: ' + content_type.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body
                    message = BytesParser(policy=policy.default).parsebytes(mime)
                    part = next((p for p in message.iter_parts() if
                                 p.get_param('name', header='content-disposition') == 'image'), None)
                    if part is None:
                        raise ValueError('missing image form field')
                    image = part.get_payload(decode=True)
                else:
                    image = body
                try:
                    result = bridge.predict(image, track)
                except urllib.error.HTTPError as exc:
                    try:
                        backend_error = json.load(exc)
                    except (ValueError, OSError):
                        backend_error = {'error': f'backend HTTP {exc.code}'}
                    self.respond(exc.code, backend_error)
                    return
                except ValueError as exc:
                    self.respond(502, {'error': 'backend evidence contract: ' + str(exc)[:180]})
                    return
                self.respond(200, result)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)[:200]})
            except Exception as exc:
                self.respond(502, {'error': type(exc).__name__ + ': ' + str(exc)[:200]})
            finally:
                self.inference_lock.release()

        def log_message(self, format, *args):
            pass  # Never log image bytes, OCR text or query paths.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8125')
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--cards', type=Path, required=True)
    parser.add_argument('--ocr-url', default='http://127.0.0.1:8129')
    parser.add_argument('--ocr-timeout', type=float, default=3.0)
    parser.add_argument('--port', type=int, default=8127)
    args = parser.parse_args()
    if urlsplit(args.backend).hostname != '127.0.0.1' or urlsplit(args.ocr_url).hostname != '127.0.0.1':
        parser.error('backend and OCR worker must bind loopback')
    if not .1 <= args.ocr_timeout <= 3:
        parser.error('--ocr-timeout must be 0.1..3 seconds')
    bridge = Bridge(args.backend, args.cards, args.catalog, args.ocr_url, args.ocr_timeout)
    print(json.dumps({'ready': True, 'backend': args.backend, 'port': args.port,
                      'catalog_version': bridge.catalog_version}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(bridge)).serve_forever()


if __name__ == '__main__':
    main()
