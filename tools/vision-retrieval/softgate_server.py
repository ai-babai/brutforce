"""Development variant B: generic wine text softens a near-miss wine gate.

No case IDs, catalog slugs, lexical scores, visual ranks, or gold answers enter
selection. This is a separately named no-training hypothesis, not a fitted gate.
"""
import argparse
import hashlib
import json
import re
import time
import unicodedata
from http.server import HTTPServer
from pathlib import Path

import server
from detector_encoder_server import RTSoVision
from fallback_server import Pipeline as FallbackPipeline
from label_context_v2 import VERSION as LABEL_CONTEXT_VERSION
from so400m_ablation import MODELS

MODEL_VERSION = 'rtdetr-r18-so400m384-soft-wine-text-gate-v1'
MAX_REJECTED_CANDIDATES = 2
MIN_WINE_MARGIN = -0.03
MIN_LABEL_SCORE = 0.15
WINE_TEXT = re.compile(
    r'(?<!\w)(?:вино|вина|винный|винная|винное|винодельня|винодельческ\w*|'
    r'полусухое|полусухой|сухое|сухой|полусладкое|полусладкий|сладкое|сладкий|'
    r'wine|winery|vino|vin)(?!\w)', re.IGNORECASE)
NONWINE_TEXT = re.compile(
    r'(?<!\w)(?:пиво|пивное|beer|lager|ale|cider|сидр|'
    r'водка|vodka|whisky|whiskey|виски|gin|джин|rum|ром|'
    r'текила|tequila|brandy|бренди|cognac|коньяк|ликер|ликёр|liqueur)(?!\w)',
    re.IGNORECASE)


class Pipeline(FallbackPipeline):
    def rescue_rejected(self, image, selection):
        started = time.perf_counter()
        attempts = []
        candidates = sorted(selection['boxes'], key=lambda item: (
            item['center_distance'], -item['score']))[:MAX_REJECTED_CANDIDATES]
        for candidate in candidates:
            evidence = {'box': candidate['box'],
                        'detector_score': candidate['score'],
                        'wine_margin': candidate['wine_margin']}
            attempts.append(evidence)
            if candidate['wine_margin'] < MIN_WINE_MARGIN:
                evidence['decision'] = 'wine_margin_too_low'
                continue
            target = image.crop(candidate['box'])
            try:
                _, label = self.model.label_region(target)
                evidence['label_source'] = label['source']
                evidence['label_score'] = label['score']
                if (not label['source'].startswith('owlv2_label')
                        or (label['score'] or 0) < MIN_LABEL_SCORE):
                    evidence['decision'] = 'no_confident_label'
                    continue
                ocr_text, ocr_ms = self._ocr_crop(target)
                normalized = unicodedata.normalize('NFKC', ocr_text).casefold()
                wine_match = WINE_TEXT.search(normalized)
                nonwine_match = NONWINE_TEXT.search(normalized)
                evidence.update(ocr_text=ocr_text, ocr_ms=ocr_ms,
                                wine_text_signal=wine_match.group(0) if wine_match else None,
                                nonwine_text_veto=nonwine_match.group(0) if nonwine_match else None)
                if nonwine_match:
                    evidence['decision'] = 'nonwine_text_veto'
                    continue
                if not wine_match:
                    evidence['decision'] = 'no_wine_text_signal'
                    continue
                evidence['decision'] = 'accepted'
                return target, {'version': MODEL_VERSION, 'accepted': True,
                                'selected_box': candidate['box'],
                                'ocr_text': ocr_text, 'ocr_ms': ocr_ms,
                                'attempts': attempts,
                                'total_ms': round((time.perf_counter()-started)*1000)}
            except Exception as exc:
                evidence['decision'] = 'rescue_error'
                evidence['error'] = type(exc).__name__ + ': ' + str(exc)[:180]
        return None, {'version': MODEL_VERSION, 'accepted': False,
                      'attempts': attempts,
                      'total_ms': round((time.perf_counter()-started)*1000)}

    def predict(self, content, track):
        result = super().predict(content, track)
        result['model_version'] = MODEL_VERSION
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
    p.add_argument('--port', type=int, default=8091)
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
