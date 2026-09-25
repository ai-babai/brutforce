#!/usr/bin/env python3
"""Isolated persistent PaddleOCR HTTP worker; input is a selected target JPEG."""
import argparse
import io
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8129)
    p.add_argument('--threads', type=int, default=2)
    a = p.parse_args()
    import numpy as np
    from PIL import Image
    from paddleocr import PaddleOCR

    start = time.perf_counter()
    ocr = PaddleOCR(device='cpu', cpu_threads=a.threads, enable_mkldnn=False,
                    text_detection_model_name='PP-OCRv5_mobile_det',
                    text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',
                    text_det_limit_side_len=1280, text_det_limit_type='max',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False)
    load_ms = round((time.perf_counter()-start)*1000)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/healthz':
                self.send_error(404)
                return
            self.respond(200, {'ready': True, 'load_ms': load_ms})

        def do_POST(self):
            if self.path != '/ocr':
                self.send_error(404)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 30_000_000:
                self.respond(400, {'error': 'invalid image size'})
                return
            content = self.rfile.read(size)
            start = time.perf_counter()
            try:
                with Image.open(io.BytesIO(content)) as image:
                    bgr = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
                result = list(ocr.predict(bgr))
                value = result[0].json['res'] if result else {}
                payload = {'texts': [str(x) for x in value.get('rec_texts', [])],
                           'scores': [float(x) for x in value.get('rec_scores', [])],
                           'ocr_ms': round((time.perf_counter()-start)*1000)}
                self.respond(200, payload)
            except Exception as exc:
                self.respond(500, {'error': type(exc).__name__ + ': ' + str(exc)[:200],
                                   'ocr_ms': round((time.perf_counter()-start)*1000)})

        def respond(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, fmt, *args):
            pass

    print(json.dumps({'ready': True, 'load_ms': load_ms, 'port': a.port}), flush=True)
    HTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
