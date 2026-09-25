import importlib.util
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('cpu_serving', Path(__file__).with_name('cpu_serving.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeEngine:
    def __init__(self, action=None):
        self.action = action

    def predict(self, content, track):
        row = {
            'branches_top20': {'whole': [{'slug': 'wine-a'}, {'slug': 'wine-b'}]},
            'timings_ms': {'total_ms': 100}, 'image_sha256': 'abc',
        }
        if self.action:
            row['action'] = self.action
        return row


class CPUServingTest(unittest.TestCase):
    def test_match_contract(self):
        pipeline = module.CPUPipeline.__new__(module.CPUPipeline)
        pipeline.engine = FakeEngine()
        result = pipeline.predict(b'image', 'service')
        self.assertEqual(result['slug'], 'wine-a')
        self.assertEqual(result['ranked_slugs'], ['wine-a', 'wine-b'])
        self.assertEqual(result['model_version'], module.MODEL_VERSION)
        self.assertNotIn('action', result)

    def test_abstention_contract(self):
        pipeline = module.CPUPipeline.__new__(module.CPUPipeline)
        pipeline.engine = FakeEngine('no_match')
        result = pipeline.predict(b'image', 'service')
        self.assertEqual(result['ranked_slugs'], [])
        self.assertEqual(result['action'], 'no_match')
        self.assertNotIn('slug', result)

    def test_retrieval_ranking(self):
        pipeline = module.CPUPipeline.__new__(module.CPUPipeline)
        pipeline.engine = FakeEngine()
        result = pipeline.predict(b'image', 'retrieval')
        self.assertEqual(result['ranked_slugs'], ['wine-a', 'wine-b'])

    def test_busy_returns_immediately_while_health_stays_available(self):
        entered, release = threading.Event(), threading.Event()

        class Base(BaseHTTPRequestHandler):
            def do_POST(self):
                entered.set()
                release.wait(timeout=5)
                self.respond(200, {'ok': True})

            def respond(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        pipeline = type('Pipeline', (), {'load_ms': 1})()
        handler = module.make_handler(Base, pipeline, 4)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        base = f'http://127.0.0.1:{server.server_port}'
        first_result = []

        def first():
            with urlopen(Request(base + '/v1/eval/predict', data=b'a'), timeout=5) as response:
                first_result.append(response.status)

        worker = threading.Thread(target=first)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            started = time.monotonic()
            with self.assertRaises(HTTPError) as busy:
                urlopen(Request(base + '/v1/eval/predict', data=b'b'), timeout=2)
            self.assertEqual(busy.exception.code, 503)
            self.assertLess(time.monotonic() - started, 1)
            with urlopen(base + '/healthz', timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(json.load(response)['busy'])
        finally:
            release.set()
            worker.join(5)
            server.shutdown()
            server.server_close()
        self.assertEqual(first_result, [200])


if __name__ == '__main__':
    unittest.main()
