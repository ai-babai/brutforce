"""Pinned F8 and automatic A2 on separate loopback ports, sharing one CPU model."""
import argparse
import hashlib
import importlib.util
import math
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

SUFFIX = '-a2-auto-v1'
F8_SHA = 'c82ce1d3671f539a811b0afa46c58395e4675969bd3b8e1aedce8ff2b7585887'


def qualifies(raw):
    selection, label = raw.get('selection') or {}, raw.get('label_selection') or {}
    score = label.get('score')
    return (selection.get('selection_reason') == 'standalone_label_no_bottle'
            and isinstance(label.get('source'), str)
            and label['source'].startswith('owlv2_label')
            and type(score) in (int, float) and math.isfinite(score) and score >= .15)


class A2View:
    """Called only while the shared HTTP inference lock is held."""
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def __getattr__(self, key):
        return getattr(self.pipeline, key)

    def predict(self, content, track):
        original = self.pipeline.engine.predict
        evidence = {'eligible': False, 'rerouted': False, 'retrieval_error': False}

        def wrapped(data, selected_track):
            started = time.perf_counter()
            raw = original(data, selected_track)
            evidence['eligible'] = selected_track == 'service' and qualifies(raw)
            if evidence['eligible']:
                try:
                    retrieved = original(data, 'retrieval')
                    ranks = retrieved['branches_top20']['whole']
                    if ranks:
                        raw['branches_top20']['whole'] = ranks
                        raw['variants_top20'] = {'whole': ranks, 'all': ranks}
                        raw['slug'] = ranks[0]['slug']
                        raw.pop('action', None)
                        evidence['rerouted'] = True
                except Exception:
                    # Preserve the first service answer, as in the frozen A2 experiment.
                    evidence['retrieval_error'] = True
            raw['timings_ms']['total_ms'] = round((time.perf_counter() - started) * 1000)
            return raw

        self.pipeline.engine.predict = wrapped
        try:
            result = self.pipeline.predict(content, track)
            result['model_version'] += SUFFIX
            result['serving_profile'] += SUFFIX
            result['a2'] = evidence
            return result
        finally:
            self.pipeline.engine.predict = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--f8-source', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--baseline-port', type=int, default=8126)
    parser.add_argument('--port', type=int, default=8127)
    args = parser.parse_args()
    with args.f8_source.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != F8_SHA:
            raise ValueError('F8 source SHA mismatch')
    spec = importlib.util.spec_from_file_location('pinned_f8', args.f8_source)
    f8 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(f8)
    pipeline = f8.CPUPipeline(args.catalog, args.index_dir, 6, 'so400m', route='onnx640')
    import server
    lock = threading.Lock()
    baseline = f8.base.make_handler(server.Handler, pipeline, 6)
    candidate = f8.base.make_handler(server.Handler, A2View(pipeline), 6)

    class CandidateHandler(candidate):
        def respond(self, status, payload):
            if self.path == '/healthz' and status == 200:
                payload = {**payload, 'model_version': payload['model_version'] + SUFFIX,
                           'serving_profile': payload['serving_profile'] + SUFFIX}
            super().respond(status, payload)

    baseline.inference_lock = CandidateHandler.inference_lock = lock
    # Bind both before serving either: a port conflict must fail the whole unit.
    old = ThreadingHTTPServer(('127.0.0.1', args.baseline_port), baseline)
    new = ThreadingHTTPServer(('127.0.0.1', args.port), CandidateHandler)
    threading.Thread(target=old.serve_forever, daemon=True).start()
    new.serve_forever()


if __name__ == '__main__':
    main()
