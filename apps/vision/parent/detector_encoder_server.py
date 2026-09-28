"""Live RT-DETR bottle + OWLv2 label + SO400M retrieval HTTP control.

Base224 remains the wine/nonwine classifier. SO400M encodes only the whole
target and label context against its separately built gated index.
"""
import argparse
import hashlib
import json
from http.server import HTTPServer
from pathlib import Path

import server
from detector_variants import DetectorVision
from label_context_v2 import VERSION as LABEL_CONTEXT_VERSION
from so400m_ablation import Embedder, MODELS


class RTSoVision(DetectorVision):
    def __init__(self, device='cuda'):
        self._classifying = False
        super().__init__(device, variant='rtdetr-r18')
        self.so_embedder = Embedder(self.device, 'so400m384')

    def select_service(self, image):
        self._classifying = True
        try:
            return super().select_service(image)
        finally:
            self._classifying = False

    def image_features(self, images, batch_size=24):
        if self._classifying:
            return super().image_features(images, batch_size)
        return self.so_embedder.features(images, batch_size)


class Handler(server.Handler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404)
            return
        self.respond(200, {
            'status': 'ready', 'detector': 'rtdetr-r18',
            'retrieval_encoder': '@'.join(MODELS['so400m384']),
            'classifier_encoder': '@'.join(MODELS['base224']),
            'cold_load_ms': self.pipeline.load_ms,
            'device': self.pipeline.device, 'gpu_name': self.pipeline.gpu_name,
            'label_crop_mode': LABEL_CONTEXT_VERSION,
        })


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--index-dir', type=Path, required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--ocr-threads', type=int, default=2)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8080)
    a = p.parse_args()
    info = json.loads((a.index_dir/'index-info.json').read_text())
    model = '@'.join(MODELS['so400m384'])
    if (info.get('model') != model or info.get('label_crop') != LABEL_CONTEXT_VERSION
            or info['catalog_manifest_sha256'] != hashlib.sha256(a.catalog.read_bytes()).hexdigest()):
        raise ValueError('SO400M index model/crop/catalog mismatch')
    server.Vision = RTSoVision
    pipeline = server.Pipeline(a.catalog, a.index_dir, a.device,
                               a.ocr_threads, label_context=True)
    Handler.pipeline = pipeline
    print(json.dumps({'ready': True, 'detector': 'rtdetr-r18',
                      'retrieval_encoder': model, 'classifier_encoder': '@'.join(MODELS['base224']),
                      'cold_load_ms': pipeline.load_ms, 'device': pipeline.device,
                      'gpu_name': pipeline.gpu_name}), flush=True)
    HTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
