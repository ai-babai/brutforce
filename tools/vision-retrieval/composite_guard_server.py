"""Development variant C: suppress weak composite bottle boxes before selection.

The pure guard uses only RT-DETR geometry and confidence. Wine classification,
center selection, label/OCR retrieval, catalog index, and RRF remain unchanged.
"""
import argparse
import hashlib
import json
from http.server import HTTPServer
from pathlib import Path

import server
from detector_encoder_server import RTSoVision
from label_context_v2 import VERSION as LABEL_CONTEXT_VERSION
from selection_guard import VERSION as GUARD_VERSION, filter_composite_candidates
from so400m_ablation import MODELS

MODEL_VERSION = 'rtdetr-r18-so400m384-composite-box-guard-v1'


class GuardVision(RTSoVision):
    def detect(self, image, threshold=.08):
        candidates, detect_ms = super().detect(image, threshold)
        retained, removed = filter_composite_candidates(candidates, image.size)
        self._last_guard_removed = removed
        return retained, detect_ms

    def select_service(self, image):
        target, selection = super().select_service(image)
        selection['guard_version'] = GUARD_VERSION
        selection['guard_suppressed'] = getattr(self, '_last_guard_removed', [])
        return target, selection


class Pipeline(server.Pipeline):
    def __init__(self, catalog_path, index_dir, device='cuda', ocr_threads=2):
        super().__init__(catalog_path, index_dir, device, ocr_threads, label_context=True)
        self.catalog_version = json.loads(Path(catalog_path).read_text())['version']
        self.index_version = json.loads((Path(index_dir) / 'index-info.json').read_text())['version']

    def predict(self, content, track):
        result = super().predict(content, track)
        if track == 'service':
            ranked = [item['slug'] for item in result['variants_top20']['all']]
            if 'slug' in result:
                assert ranked and result['slug'] == ranked[0]
            else:
                ranked = []
            result['ranked_slugs'] = ranked
        result.update(catalog_version=self.catalog_version,
                      index_version=self.index_version,
                      model_version=MODEL_VERSION)
        return result


class Handler(server.Handler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404)
            return
        self.respond(200, {'status': 'ready', 'catalog_version': self.pipeline.catalog_version,
                           'index_version': self.pipeline.index_version,
                           'model_version': MODEL_VERSION,
                           'cold_load_ms': self.pipeline.load_ms,
                           'device': self.pipeline.device, 'gpu_name': self.pipeline.gpu_name,
                           'label_crop_mode': LABEL_CONTEXT_VERSION,
                           'guard_version': GUARD_VERSION})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--index-dir', type=Path, required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--ocr-threads', type=int, default=2)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8092)
    a = p.parse_args()
    info = json.loads((a.index_dir / 'index-info.json').read_text())
    model = '@'.join(MODELS['so400m384'])
    if (info.get('model') != model or info.get('label_crop') != LABEL_CONTEXT_VERSION
            or info['catalog_manifest_sha256'] != hashlib.sha256(a.catalog.read_bytes()).hexdigest()):
        raise ValueError('SO400M index model/crop/catalog mismatch')
    server.Vision = GuardVision
    pipeline = Pipeline(a.catalog, a.index_dir, a.device, a.ocr_threads)
    Handler.pipeline = pipeline
    print(json.dumps({'ready': True, 'catalog_version': pipeline.catalog_version,
                      'index_version': pipeline.index_version,
                      'model_version': MODEL_VERSION,
                      'cold_load_ms': pipeline.load_ms, 'device': pipeline.device,
                      'gpu_name': pipeline.gpu_name}), flush=True)
    HTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
