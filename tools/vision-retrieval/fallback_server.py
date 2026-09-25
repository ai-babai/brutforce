"""One no-training rescue for RT-DETR bottles rejected by the wine gate.

The decision uses independent OWLv2 label localization, PaddleOCR catalog text,
and SO400M label retrieval. It never reads case IDs or evaluation answers.
"""
import argparse
import hashlib
import io
import json
import time
from http.server import HTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

import server
from detector_encoder_server import RTSoVision
from label_context_v2 import context_box, VERSION as LABEL_CONTEXT_VERSION
from ranking import top
from so400m_ablation import MODELS

MODEL_VERSION = 'rtdetr-r18-so400m384-winegate-labelocr-rescue-v1'
MAX_REJECTED_CANDIDATES = 2
MIN_LABEL_SCORE = 0.15
MIN_OCR_CATALOG_SCORE = 0.35
OCR_VISUAL_AGREEMENT_RANK = 3


class Pipeline(server.Pipeline):
    def __init__(self, catalog_path, index_dir, device='cuda', ocr_threads=2):
        super().__init__(catalog_path, index_dir, device, ocr_threads, label_context=True)
        self.catalog_version = json.loads(Path(catalog_path).read_text())['version']
        self.index_version = json.loads((Path(index_dir) / 'index-info.json').read_text())['version']

    def _ocr_crop(self, target):
        # Same JPEG-92 preprocessing and recognition threshold as the baseline.
        t = time.perf_counter()
        buf = io.BytesIO()
        target.save(buf, 'JPEG', quality=92)
        with Image.open(io.BytesIO(buf.getvalue())) as encoded:
            ocr_image = np.asarray(encoded.convert('RGB'))[:, :, ::-1].copy()
        result = list(self.ocr.predict(ocr_image))
        res = result[0].json['res'] if result else {}
        text = '\n'.join(str(v) for v, score in zip(
            res.get('rec_texts', []), res.get('rec_scores', [])) if float(score) >= .35)
        return text, round((time.perf_counter() - t) * 1000)

    def rescue_rejected(self, image, selection):
        started = time.perf_counter()
        attempts = []
        candidates = sorted(selection['boxes'], key=lambda item: (
            item['center_distance'], -item['score']))[:MAX_REJECTED_CANDIDATES]
        for candidate in candidates:
            target = image.crop(candidate['box'])
            try:
                _, label = self.model.label_region(target)
                evidence = {'box': candidate['box'], 'detector_score': candidate['score'],
                            'wine_margin': candidate['wine_margin'],
                            'label_source': label['source'], 'label_score': label['score']}
                attempts.append(evidence)
                if not label['source'].startswith('owlv2_label') or (label['score'] or 0) < MIN_LABEL_SCORE:
                    evidence['decision'] = 'no_confident_label'
                    continue
                text, ocr_ms = self._ocr_crop(target)
                evidence['ocr_ms'] = ocr_ms
                evidence['ocr_text'] = text
                ocr_scores = self.lexical.scores(text)
                ocr_matches = top(ocr_scores, self.slugs, OCR_VISUAL_AGREEMENT_RANK)
                evidence['ocr_catalog_top3'] = ocr_matches
                if not ocr_matches or ocr_matches[0]['score'] < MIN_OCR_CATALOG_SCORE:
                    evidence['decision'] = 'weak_catalog_text'
                    continue
                region = target.crop(context_box(target.size, label['box']))
                feature = self.model.image_features([region])[0]
                scores = np.where(np.isfinite(self.label).all(axis=1),
                                  self.label @ feature, np.nan)
                label_matches = top(scores, self.slugs)
                agreement = {item['slug'] for item in ocr_matches}.intersection(
                    item['slug'] for item in label_matches)
                evidence['label_top20'] = label_matches
                evidence['agreement_slugs'] = sorted(agreement)
                if not agreement:
                    evidence['decision'] = 'ocr_visual_disagree'
                    continue
                evidence['decision'] = 'accepted'
                return target, {'version': MODEL_VERSION, 'accepted': True,
                                'selected_box': candidate['box'], 'ocr_text': text,
                                'ocr_ms': ocr_ms, 'attempts': attempts,
                                'total_ms': round((time.perf_counter()-started)*1000)}
            except Exception as exc:
                attempts.append({'box': candidate['box'],
                                 'decision': 'rescue_error',
                                 'error': type(exc).__name__ + ': ' + str(exc)[:180]})
        return None, {'version': MODEL_VERSION, 'accepted': False,
                      'attempts': attempts,
                      'total_ms': round((time.perf_counter()-started)*1000)}

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
                           'label_crop_mode': LABEL_CONTEXT_VERSION})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--index-dir', type=Path, required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--ocr-threads', type=int, default=2)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8080)
    a = p.parse_args()
    info = json.loads((a.index_dir / 'index-info.json').read_text())
    model = '@'.join(MODELS['so400m384'])
    if (info.get('model') != model or info.get('label_crop') != LABEL_CONTEXT_VERSION
            or info['catalog_manifest_sha256'] != hashlib.sha256(a.catalog.read_bytes()).hexdigest()):
        raise ValueError('SO400M index model/crop/catalog mismatch')
    server.Vision = RTSoVision
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
