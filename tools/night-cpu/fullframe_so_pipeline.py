"""Separate C3 routing ablation: SO400M full frame if no bottle is detected.

The served all list is an explicit compatibility alias of whole.
No routine label pass, label embedding, OCR, or fusion runs per request.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from http.server import HTTPServer
from pathlib import Path


VERSION = 'rtdetr-so400m-fullframe-nobottle-v1'
MODEL = 'google/siglip2-so400m-patch16-384@dd658faac399427308559e2c3ac1e99cbe43845d'
LABEL_CROP = 'owlv2-label-context-union-v2'


def validate_index_info(info: dict, catalog_bytes: bytes) -> None:
    if info.get('model') != MODEL:
        raise ValueError('SO400M index model mismatch')
    if info.get('label_crop') != LABEL_CROP:
        raise ValueError('SO400M index reference-crop version mismatch')
    if info.get('catalog_manifest_sha256') != hashlib.sha256(catalog_bytes).hexdigest():
        raise ValueError('SO400M index catalog mismatch')


def prediction(track: str, target_found: bool, ranked: list[dict]) -> dict:
    if track == 'service':
        if not target_found:
            return {'action': 'no_match'}
        return {'slug': ranked[0]['slug']} if ranked else {'action': 'insufficient_information'}
    if track == 'retrieval':
        return {'ranked_slugs': [item['slug'] for item in ranked]}
    raise ValueError('track')


class Pipeline:
    def __init__(self, catalog_path: Path, index_dir: Path, device: str):
        import numpy as np
        from detector_encoder_server import RTSoVision

        started = time.perf_counter()
        catalog_bytes = catalog_path.read_bytes()
        info = json.loads((index_dir / 'index-info.json').read_text())
        validate_index_info(info, catalog_bytes)
        refs = json.loads(catalog_bytes)['references']
        self.slugs = [item['slug'] for item in refs]
        index = np.load(index_dir / 'index.npz')
        if list(index['slugs']) != self.slugs:
            raise ValueError('catalog/index slug order mismatch')
        self.full = index['full']
        if len(self.full) != len(self.slugs):
            raise ValueError('full-index row count mismatch')
        self.model = RTSoVision(device)
        self.device = self.model.device
        self.gpu_name = (self.model.torch.cuda.get_device_name(0)
                         if self.device.startswith('cuda') else None)
        self.load_ms = round((time.perf_counter() - started) * 1000)

    def predict(self, content: bytes, track: str) -> dict:
        import numpy as np
        from PIL import Image, ImageOps
        from ranking import top

        if track not in ('service', 'retrieval'):
            raise ValueError('track')
        started = time.perf_counter()
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        stage = {'decode_ms': round((time.perf_counter() - started) * 1000),
                 'detect_ms': 0, 'class_ms': 0, 'label_detect_ms': 0,
                 'whole_embedding_ms': 0, 'label_embedding_ms': 0,
                 'ocr_ms': 0, 'rank_ms': 0, 'fusion_ms': 0}
        standalone = None
        if track == 'service':
            target, selection = self.model.select_service(image)
            stage['detect_ms'] = selection['detect_ms']
            stage['class_ms'] = selection['class_ms']
            if target is None and selection['selection_reason'] == 'no_bottle_detected':
                target = image
                selection['selected_box'] = [0, 0, *image.size]
                selection['selection_reason'] = 'fullframe_no_bottle_hypothesis'
        else:
            target = image
            selection = {'boxes': [], 'selected_box': [0, 0, *image.size],
                         'selection_reason': 'verified_retrieval_crop'}
        ranked = []
        if target is not None:
            step = time.perf_counter()
            feature = self.model.image_features([target])[0]
            stage['whole_embedding_ms'] = round((time.perf_counter() - step) * 1000)
            step = time.perf_counter()
            scores = np.where(np.isfinite(self.full).all(axis=1),
                              self.full @ feature, np.nan)
            ranked = top(scores, self.slugs)
            stage['rank_ms'] = round((time.perf_counter() - step) * 1000)
        stage['total_ms'] = round((time.perf_counter() - started) * 1000)
        return {**prediction(track, target is not None, ranked),
                'track': track, 'timings_ms': stage,
                'selection': selection, 'label_selection': standalone,
                'label_context_box': None, 'label_crop_mode': 'not-used-whole-only',
                'branches_top20': {'whole': ranked},
                'variants_top20': {'whole': ranked, 'all': ranked},
                'served_variant': 'whole', 'all_alias': 'whole',
                'architecture_version': VERSION,
                'ocr_text': '', 'ocr_error': None,
                'image_sha256': hashlib.sha256(content).hexdigest()}


def main() -> None:
    import server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    pipeline = Pipeline(args.catalog, args.index_dir, args.device)

    class Handler(server.Handler):
        def do_GET(self):
            if self.path != '/healthz':
                self.send_error(404)
                return
            self.respond(200, {'status': 'ready', 'architecture_version': VERSION,
                               'detector': 'rtdetr-r18', 'retrieval_encoder': MODEL,
                               'classifier_encoder': 'base224',
                               'served_variant': 'whole', 'all_alias': 'whole',
                               'cold_load_ms': self.pipeline.load_ms,
                               'device': self.pipeline.device,
                               'gpu_name': self.pipeline.gpu_name})

    Handler.pipeline = pipeline
    print(json.dumps({'ready': True, 'architecture_version': VERSION,
                      'served_variant': 'whole', 'all_alias': 'whole',
                      'cold_load_ms': pipeline.load_ms, 'device': pipeline.device,
                      'gpu_name': pipeline.gpu_name,
                      'host': args.host, 'port': args.port}), flush=True)
    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
