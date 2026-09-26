"""P1 development route: inspect a physical target before accepting a negative wine gate.

The RT-DETR, Base224 classifier, SO400M index, OWLv2 and PaddleOCR are the
existing pinned components. Neither candidate retrieval nor catalog text enters
physical target selection or the decision to reopen a rejected wine gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import unicodedata
from http.server import HTTPServer
from pathlib import Path

import server
from detector_encoder_server import RTSoVision
from fallback_server import Pipeline as ExistingPipeline
from label_context_v2 import VERSION as LABEL_CONTEXT_VERSION, context_box
from softgate_server import NONWINE_TEXT, WINE_TEXT
from so400m_ablation import MODELS


VERSION = 'rtdetr-so400m-delayed-target-gate-p1-v1'
MIN_BOTTLE_SCORE = .25
MIN_LABEL_SCORE = .15
MAX_PHYSICAL_HYPOTHESES = 2


def physical_hypotheses(boxes: list[dict]) -> list[dict]:
    """Choose by scene geometry and detection confidence, never catalog match."""
    credible = (box for box in boxes if box['score'] >= MIN_BOTTLE_SCORE)
    return sorted(credible, key=lambda b: (b['center_distance'], -b['score']))[:MAX_PHYSICAL_HYPOTHESES]


def text_evidence(text: str) -> dict:
    normalized = unicodedata.normalize('NFKC', text).casefold()
    wine = WINE_TEXT.search(normalized)
    nonwine = NONWINE_TEXT.search(normalized)
    return {'wine_text_signal': wine.group(0) if wine else None,
            'nonwine_text_veto': nonwine.group(0) if nonwine else None}


def overlap_fraction(box: list[int], other: list[int]) -> float:
    area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
    return (max(0, min(box[2], other[2]) - max(box[0], other[0]))
            * max(0, min(box[3], other[3]) - max(box[1], other[1])) / area)


class Pipeline(ExistingPipeline):
    def rescue_rejected(self, image, selection):
        started = time.perf_counter()
        hypotheses = physical_hypotheses(selection['boxes'])
        trace = {'version': VERSION, 'accepted': False, 'route': 'rejected_bottle',
                 'physical_hypotheses': [
                     {'target_id': index, 'box': item['box'], 'detector_score': item['score'],
                      'center_distance': item['center_distance'], 'wine_margin': item['wine_margin']}
                     for index, item in enumerate(hypotheses)], 'attempts': []}
        # Weak, peripheral false bottle detections must not suppress IMG-02.
        # This separate label-only route searches the full image for a label.
        if not hypotheses:
            trace['route'] = 'standalone_label_after_false_bottle'
            target = image
            target_box = [0, 0, *image.size]
            target_id = 'standalone_label'
        else:
            # The first physical target is chosen before any reading/retrieval.
            # A recognized catalog neighbor cannot replace it if reading fails.
            chosen = hypotheses[0]
            target_box = chosen['box']
            target = image.crop(target_box)
            target_id = 0
        evidence = {'target_id': target_id, 'target_box': target_box,
                    'target_sha256': hashlib.sha256(target.tobytes()).hexdigest()}
        trace['attempts'].append(evidence)
        try:
            _, label = self.model.label_region(target)
            evidence.update(label_source=label['source'], label_score=label['score'],
                            label_box=label['box'])
            if (not label['source'].startswith('owlv2_label')
                    or (label['score'] or 0) < MIN_LABEL_SCORE):
                evidence['decision'] = 'no_confident_label'
                return None, self._finish(trace, started)
            # OCR reads the selected target's label context only. A composite
            # whole-bottle visual crop never contributes a neighbor's OCR.
            label_box = (label['box'] if not hypotheses
                         else context_box(target.size, label['box']))
            evidence['ocr_box_within_target'] = label_box
            if len(hypotheses) > 1:
                absolute = [label_box[0] + target_box[0], label_box[1] + target_box[1],
                            label_box[2] + target_box[0], label_box[3] + target_box[1]]
                overlap = overlap_fraction(absolute, hypotheses[1]['box'])
                evidence['competing_target_overlap'] = overlap
                if overlap > .15:
                    evidence['decision'] = 'competing_target_label_overlap'
                    return None, self._finish(trace, started)
            text, ocr_ms = self._ocr_crop(target.crop(label_box))
            signals = text_evidence(text)
            evidence.update(ocr_text=text, ocr_ms=ocr_ms, **signals)
            if signals['nonwine_text_veto']:
                evidence['decision'] = 'nonwine_text_veto'
            elif not signals['wine_text_signal']:
                evidence['decision'] = 'no_wine_text_signal'
            else:
                evidence['decision'] = 'accepted'
                trace.update(accepted=True, selected_box=target_box,
                             target_id=target_id, ocr_text=text, ocr_ms=ocr_ms)
                if trace['route'] == 'standalone_label_after_false_bottle':
                    # Use only the independently localized label as query;
                    # the old full-frame false bottle is not a physical target.
                    trace['selected_box'] = label['box']
                    target = target.crop(label['box'])
                    evidence['target_sha256'] = hashlib.sha256(target.tobytes()).hexdigest()
                return target, self._finish(trace, started)
        except Exception as exc:
            evidence.update(decision='rescue_error',
                            error=type(exc).__name__ + ': ' + str(exc)[:180])
        return None, self._finish(trace, started)

    @staticmethod
    def _finish(trace, started):
        trace['total_ms'] = round((time.perf_counter() - started) * 1000)
        return trace

    def predict(self, content, track):
        result = super().predict(content, track)
        result['model_version'] = VERSION
        if track == 'service':
            rescue = result['rescue']
            if rescue and any(item['decision'] == 'rescue_error'
                              for item in rescue['attempts']):
                result.pop('slug', None)
                result['action'] = 'insufficient_information'
            result['ranked_slugs'] = ([item['slug'] for item in result['variants_top20']['all']]
                                      if 'slug' in result else [])
            chosen = result['selection'].get('selected_box')
            boxes = result['selection']['boxes']
            hypotheses = (rescue['physical_hypotheses'] if rescue else [
                {'target_id': index, 'box': item['box'],
                 'detector_score': item['score'],
                 'center_distance': item['center_distance'],
                 'wine_margin': item['wine_margin']}
                for index, item in enumerate(physical_hypotheses(boxes))])
            contained = []
            for item in boxes:
                box = item['box']
                if (not chosen or box == chosen or item['score'] < MIN_BOTTLE_SCORE
                        or overlap_fraction(box, chosen) <= .85
                        or (box[2] - box[0]) * (box[3] - box[1]) >= .7 *
                        (chosen[2] - chosen[0]) * (chosen[3] - chosen[1])):
                    continue
                if all(overlap_fraction(box, prior) < .2
                       and overlap_fraction(prior, box) < .2 for prior in contained):
                    contained.append(box)
                if len(contained) == 2:
                    break
            result['target_provenance'] = {
                'source': (rescue['route'] if rescue and rescue['accepted'] else
                           result['selection']['selection_reason']),
                'selected_box': chosen,
                'target_id': (rescue['target_id'] if rescue and rescue['accepted'] else
                              next((index for index, item in enumerate(boxes)
                                    if item['box'] == chosen), None)),
                'physical_hypotheses': hypotheses,
                'contained_bottle_boxes': contained,
                'composite_target_uncertain': len(contained) >= 2,
                'selection_used_catalog': False,
            }
        return result


class Handler(server.Handler):
    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404)
            return
        self.respond(200, {'status': 'ready', 'model_version': VERSION,
                           'catalog_version': self.pipeline.catalog_version,
                           'index_version': self.pipeline.index_version,
                           'cold_load_ms': self.pipeline.load_ms,
                           'device': self.pipeline.device,
                           'gpu_name': self.pipeline.gpu_name,
                           'label_crop_mode': LABEL_CONTEXT_VERSION})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--ocr-threads', type=int, default=2)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8092)
    args = parser.parse_args()
    info = json.loads((args.index_dir / 'index-info.json').read_text())
    if (info.get('model') != '@'.join(MODELS['so400m384'])
            or info.get('label_crop') != LABEL_CONTEXT_VERSION
            or info.get('catalog_manifest_sha256') != hashlib.sha256(args.catalog.read_bytes()).hexdigest()):
        raise ValueError('SO400M index/crop/catalog mismatch')
    server.Vision = RTSoVision
    pipeline = Pipeline(args.catalog, args.index_dir, args.device, args.ocr_threads)
    Handler.pipeline = pipeline
    print(json.dumps({'ready': True, 'model_version': VERSION,
                      'cold_load_ms': pipeline.load_ms, 'device': pipeline.device,
                      'gpu_name': pipeline.gpu_name}), flush=True)
    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
