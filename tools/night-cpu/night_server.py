"""Isolated gold-blind CPU HTTP bridge for paired whole-only encoder profiles.

Uses whole_encoder_server.Pipeline without changing its ranking behavior.
No private evaluation labels are loaded by this process.
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import re
import resource
import sys
import threading
import time
import unicodedata
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

CATALOG_VERSION = 'organizer-catalog-20260919'
INDEX_VERSIONS = {'so400m': 'so400m384-owlv2-v2-crops-reference-gated-20260925',
                  'base224': 'reference-gate-20260925-v2'}
MODEL_VERSIONS = {'so400m': 'rtdetr-so400m-whole-only-v1',
                  'base224': 'rtdetr-base224-whole-only-v1'}
WINE_TEXT = re.compile(
    r'(?<!\w)(?:вино|вина|винный|винная|винное|винодельня|винодельческ\w*|'
    r'полусухое|полусухой|сухое|сухой|полусладкое|полусладкий|сладкое|сладкий|'
    r'wine|winery|vino|vin)(?!\w)', re.IGNORECASE)
NONWINE_TEXT = re.compile(
    r'(?<!\w)(?:пиво|пивное|beer|lager|ale|cider|сидр|'
    r'водка|vodka|whisky|whiskey|виски|gin|джин|rum|ром|'
    r'текила|tequila|brandy|бренди|cognac|коньяк|ликер|ликёр|liqueur)(?!\w)',
    re.IGNORECASE)


class CPUPipeline:
    def __init__(self, catalog: Path, index_dir: Path, threads: int, encoder: str,
                  ocr_url: str | None = None, route: str = 'standard',
                  ocr_policy: str = 'all', evidence_url: str | None = None,
                  evidence_cards: Path | None = None, evidence_timeout: float = 2.0):
        import torch
        if bool(evidence_url) != bool(evidence_cards):
            raise ValueError('evidence URL and catalog cards must be supplied together')
        if evidence_url and (encoder != 'so400m' or route != 'onnx640' or ocr_url):
            raise ValueError('evidence hook requires isolated SO400M onnx640 without lexical OCR')
        if route == 'fullframe' and not ocr_url:
            raise ValueError('fullframe routing requires OCR confirmation')
        if route == 'softgate' and (encoder != 'so400m' or not ocr_url):
            raise ValueError('softgate routing requires SO400M and OCR evidence')
        if route in ('onnx640', 'onnx_dual', 'onnx_int8') and encoder != 'so400m':
            raise ValueError('ONNX routing requires SO400M')
        if route in ('onnx640', 'onnx_int8'):
            module_name = 'onnx_so_pipeline'
        elif route == 'onnx_dual':
            module_name = 'onnx_dual_pipeline'
        elif route == 'fullframe':
            module_name = 'fullframe_so_pipeline' if encoder == 'so400m' else 'fullframe_pipeline'
        elif route in ('owl640', 'softgate'):
            module_name = 'fast_owl_pipeline'
        else:
            module_name = 'whole_encoder_server' if encoder == 'so400m' else 'base224_pipeline'
        module = importlib.import_module(module_name)
        Pipeline = (module.SO640Pipeline if route in ('owl640', 'softgate') and encoder == 'so400m' else
                    module.Base640Pipeline if route == 'owl640' else module.Pipeline)

        catalog_info = json.loads(catalog.read_text())
        index_info = json.loads((index_dir / 'index-info.json').read_text())
        if catalog_info.get('version') != CATALOG_VERSION:
            raise ValueError('catalog version mismatch')
        if encoder == 'so400m' and index_info.get('version') != INDEX_VERSIONS[encoder]:
            raise ValueError('index version mismatch')
        if encoder == 'base224' and index_info.get('reference_gate', {}).get('version') != INDEX_VERSIONS[encoder]:
            raise ValueError('index reference gate mismatch')
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(1)
        self.engine = Pipeline(catalog, index_dir, 'cpu')
        self.load_ms = self.engine.load_ms
        self.encoder = encoder
        self.route = route
        self.ocr_url = ocr_url
        self.ocr_policy = ocr_policy
        self.evidence_url = evidence_url
        self.evidence_timeout = evidence_timeout
        self.profile = encoder + '-' + route + ('-ocr-' + ocr_policy if ocr_url else '') + (
            '-evidence-v1' if evidence_url else '')
        if evidence_url:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cpu-evidence'))
            from matcher import Matcher
            self.matcher = Matcher(json.loads(evidence_cards.read_text()),
                                   [ref['slug'] for ref in catalog_info['references']])
        if ocr_url:
            from ranking import Lexical
            refs = catalog_info['references']
            self.lexical = Lexical([{'slug': r['slug'], 'title': r.get('title', ''),
                                    'producer': r.get('winery', '')} for r in refs])
            self.slugs = [r['slug'] for r in refs]

    def _ocr_target(self, target):
        from fuse import ocr_top
        started = time.perf_counter()
        image_out = io.BytesIO()
        target.save(image_out, 'JPEG', quality=92)
        request = urllib.request.Request(self.ocr_url + '/ocr', data=image_out.getvalue(),
                                         method='POST', headers={'Content-Type': 'image/jpeg'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.load(response)
            text = '\n'.join(str(t) for t, score in zip(value['texts'], value['scores'])
                             if float(score) >= .35)
            return text, ocr_top(self.lexical, text, self.slugs), None, round((time.perf_counter()-started)*1000)
        except Exception as exc:
            return '', [], type(exc).__name__ + ': ' + str(exc)[:200], round((time.perf_counter()-started)*1000)

    def _evidence_rerank(self, content, raw, ranks, track):
        import hashlib
        from PIL import Image, ImageOps

        started = time.perf_counter()
        positions = self.matcher.family_positions(ranks)
        diag = {'state': 'not_eligible', 'before': [x['slug'] for x in ranks],
                'after': [x['slug'] for x in ranks], 'family_positions_1based':
                [i + 1 for i in positions], 'target_box': raw['selection']['selected_box'],
                'target_sha256': None, 'ocr_error': None, 'ocr_texts': [], 'ocr_scores': [],
                'worker_ocr_ms': None, 'candidate_evidence': [], 'observations': []}
        if raw['selection']['selected_box'] is None:
            diag['state'] = 'no_selected_target'
            return ranks, diag, round((time.perf_counter()-started)*1000)
        if not positions:
            return ranks, diag, round((time.perf_counter()-started)*1000)

        box = raw['selection']['selected_box']
        # An overlapping detector box may be a second physical bottle; do not
        # assign its writing to the selected target without a separate polygon.
        if track == 'service':
            area = max(1, (box[2]-box[0]) * (box[3]-box[1]))
            for other in raw['selection']['boxes']:
                candidate = other['box']
                if candidate == box:
                    continue
                intersection = max(0, min(box[2], candidate[2])-max(box[0], candidate[0])) * (
                    max(0, min(box[3], candidate[3])-max(box[1], candidate[1])))
                if intersection / area > .2:
                    diag['state'] = 'target_overlaps_other_bottle'
                    return ranks, diag, round((time.perf_counter()-started)*1000)
        try:
            with Image.open(io.BytesIO(content)) as source:
                target = ImageOps.exif_transpose(source).convert('RGB').crop(box)
            image_out = io.BytesIO()
            target.save(image_out, 'JPEG', quality=92)
            data = image_out.getvalue()
            diag['target_sha256'] = hashlib.sha256(data).hexdigest()
            request = urllib.request.Request(self.evidence_url.rstrip('/') + '/ocr',
                data=data, method='POST', headers={'Content-Type': 'image/jpeg'})
            with urllib.request.urlopen(request, timeout=self.evidence_timeout) as response:
                value = json.load(response)
            if 'error' in value:
                raise ValueError(str(value['error'])[:200])
            texts, scores = value['texts'], value['scores']
            if not isinstance(texts, list) or not isinstance(scores, list):
                raise ValueError('invalid OCR arrays')
            diag['ocr_texts'], diag['ocr_scores'] = texts, scores
            diag['worker_ocr_ms'] = value.get('ocr_ms')
            ranks, matched = self.matcher.rerank(ranks, positions, texts, scores)
            diag.update(matched)
        except Exception as exc:
            diag['state'] = 'ocr_failed'
            diag['ocr_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
        return ranks, diag, round((time.perf_counter()-started)*1000)

    def _softgate_rescue(self, raw, content):
        import numpy as np
        from PIL import Image, ImageOps
        from ranking import top
        started = time.perf_counter()
        attempts = []
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        candidates = sorted(raw['selection']['boxes'], key=lambda item: (
            item['center_distance'], -item['score']))[:2]
        for candidate in candidates:
            entry = {'box': candidate['box'], 'wine_margin': candidate['wine_margin']}
            attempts.append(entry)
            if candidate['wine_margin'] < -.03:
                entry['decision'] = 'wine_margin_too_low'
                continue
            try:
                target = image.crop(candidate['box'])
                _, label = self.engine.model.label_region(target)
                entry['label_source'], entry['label_score'] = label['source'], label['score']
                if not label['source'].startswith('owlv2_label') or (label['score'] or 0) < .15:
                    entry['decision'] = 'no_confident_label'
                    continue
                ocr_text, ocr_ranks, ocr_error, ocr_ms = self._ocr_target(target)
                normalized = unicodedata.normalize('NFKC', ocr_text).casefold()
                wine = WINE_TEXT.search(normalized)
                nonwine = NONWINE_TEXT.search(normalized)
                entry.update({'ocr_ms': ocr_ms, 'wine_text_signal': bool(wine),
                              'nonwine_text_veto': bool(nonwine), 'ocr_error': ocr_error})
                if nonwine or not wine:
                    entry['decision'] = 'nonwine_text_veto' if nonwine else 'no_wine_text_signal'
                    continue
                step = time.perf_counter()
                feature = self.engine.model.image_features([target])[0]
                scores = np.where(np.isfinite(self.engine.full).all(axis=1),
                                  self.engine.full @ feature, np.nan)
                ranking = top(scores, self.engine.slugs)
                raw['branches_top20']['whole'] = ranking
                raw['selection']['selected_box'] = candidate['box']
                raw['selection']['selection_reason'] = 'soft_wine_text_gate'
                raw.pop('action', None)
                raw['slug'] = ranking[0]['slug'] if ranking else None
                raw['timings_ms']['whole_embedding_ms'] = round((time.perf_counter()-step)*1000)
                entry['decision'] = 'accepted'
                raw['timings_ms']['rescue_ms'] = round((time.perf_counter()-started)*1000)
                raw['timings_ms']['total_ms'] += raw['timings_ms']['rescue_ms']
                return raw, (ocr_text, ocr_ranks, ocr_error, ocr_ms), attempts
            except Exception as exc:
                entry['decision'] = 'rescue_error'
                entry['error'] = type(exc).__name__ + ': ' + str(exc)[:180]
        raw['timings_ms']['rescue_ms'] = round((time.perf_counter()-started)*1000)
        raw['timings_ms']['total_ms'] += raw['timings_ms']['rescue_ms']
        return raw, None, attempts

    def predict(self, content: bytes, track: str) -> dict:
        raw = self.engine.predict(content, track)
        rescue_ocr = None
        rescue_attempts = None
        if (self.route == 'softgate' and track == 'service' and
                raw['selection']['selection_reason'] == 'detected_bottles_classified_nonwine'):
            raw, rescue_ocr, rescue_attempts = self._softgate_rescue(raw, content)
        ranks = raw['branches_top20']['whole']
        if self.route == 'onnx_dual':
            from fuse import rank_fuse
            ranks = rank_fuse({'whole': raw['branches_top20']['whole'],
                               'label': raw['branches_top20']['label']})
        ocr_ranks = []
        ocr_text = ''
        ocr_error = None
        use_ocr = bool(self.ocr_url and raw['selection']['selected_box'] is not None and
                       (self.ocr_policy == 'all' or
                        raw['selection']['selection_reason'] in
                        ('fullframe_no_bottle_hypothesis', 'soft_wine_text_gate')))
        if use_ocr:
            from PIL import Image, ImageOps
            from fuse import rank_fuse
            started = time.perf_counter()
            if rescue_ocr is not None:
                ocr_text, ocr_ranks, ocr_error, _ = rescue_ocr
                raw['timings_ms']['ocr_ms'] = 0
            else:
                with Image.open(io.BytesIO(content)) as source:
                    source = ImageOps.exif_transpose(source).convert('RGB')
                selected = source.crop(raw['selection']['selected_box'])
                ocr_text, ocr_ranks, ocr_error, _ = self._ocr_target(selected)
                raw['timings_ms']['ocr_ms'] = round((time.perf_counter()-started)*1000)
            ranks = rank_fuse({'whole': ranks, 'ocr': ocr_ranks})
        raw['timings_ms']['total_ms'] += raw['timings_ms']['ocr_ms']
        evidence = None
        if self.evidence_url:
            ranks, evidence, evidence_ms = self._evidence_rerank(content, raw, ranks, track)
            raw['timings_ms']['evidence_ms'] = evidence_ms
            raw['timings_ms']['ocr_ms'] = evidence_ms if evidence['target_sha256'] else 0
            raw['timings_ms']['total_ms'] += evidence_ms
        rejected_fullframe = False
        if self.route == 'fullframe' and raw['selection']['selection_reason'] == 'fullframe_no_bottle_hypothesis':
            visual_set = {x['slug'] for x in raw['branches_top20']['whole']}
            agreed = bool(len(ocr_text.strip()) >= 8 and ocr_ranks and
                          ocr_ranks[0]['slug'] in visual_set)
            if not agreed:
                ranks = []
                rejected_fullframe = True
        ranked_slugs = list(dict.fromkeys(item['slug'] for item in ranks))[:20]
        if track == 'service' and raw.get('action'):
            ranked_slugs = []
        result = {
            'catalog_version': CATALOG_VERSION,
            'index_version': INDEX_VERSIONS[self.encoder],
            'model_version': MODEL_VERSIONS[self.encoder] + '-' + self.route +
                             ('-ocr-' + self.ocr_policy if self.ocr_url else '') +
                             ('-evidence-v1' if self.evidence_url else ''),
            'serving_profile': self.profile,
            'ranked_slugs': ranked_slugs,
            'timings_ms': raw['timings_ms'],
            'image_sha256': raw['image_sha256'],
        }
        if self.ocr_url:
            result.update({'branches_top20': {'whole': raw['branches_top20']['whole'],
                                               'ocr': ocr_ranks},
                           'ocr_text': ocr_text, 'ocr_error': ocr_error,
                           'ocr_used': use_ocr,
                           'selection_reason': raw['selection']['selection_reason'],
                           'fullframe_rejected': rejected_fullframe,
                           'rescue_attempts': rescue_attempts})
        elif self.route == 'onnx_dual':
            result['branches_top20'] = {'whole': raw['branches_top20']['whole'],
                                        'label': raw['branches_top20']['label']}
            result['label_selection'] = raw['label_selection']
            result['label_context_box'] = raw['label_context_box']
        if evidence is not None:
            result['evidence'] = evidence
            result['ocr_error'] = evidence['ocr_error']
            result['ocr_text'] = '\n'.join(evidence['ocr_texts'])
            result['ocr_used'] = evidence['target_sha256'] is not None
        if track == 'service':
            if ranked_slugs:
                result['slug'] = ranked_slugs[0]
            else:
                result['action'] = ('no_match' if rejected_fullframe else
                                    raw.get('action', 'insufficient_information'))
        return result


def make_handler(base_handler, pipeline, threads: int):
    class Handler(base_handler):
        inference_lock = threading.Lock()

        def do_POST(self):
            if not self.inference_lock.acquire(blocking=False):
                self.respond(503, {'error': 'vision inference busy'})
                return
            try:
                super().do_POST()
            finally:
                self.inference_lock.release()

        def respond(self, status, payload):
            try:
                super().respond(status, payload)
            except (BrokenPipeError, ConnectionResetError):
                # A timed-out client may disconnect while inference finishes.
                # Its result is discarded; the inference lock is still released.
                pass

        def do_GET(self):
            if self.path != '/healthz':
                self.send_error(404)
                return
            self.respond(200, {
                'status': 'ready',
                'catalog_version': CATALOG_VERSION,
                'index_version': INDEX_VERSIONS[self.pipeline.encoder],
                'model_version': MODEL_VERSIONS[self.pipeline.encoder] + '-' + self.pipeline.route +
                                 ('-ocr-' + self.pipeline.ocr_policy if self.pipeline.ocr_url else '') +
                                 ('-evidence-v1' if self.pipeline.evidence_url else ''),
                'serving_profile': self.pipeline.profile,
                'device': 'cpu',
                'threads': threads,
                'cold_load_ms': self.pipeline.load_ms,
                'busy': self.inference_lock.locked(),
                'max_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })

    Handler.pipeline = pipeline
    return Handler


def main() -> None:
    import server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8125)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--encoder', choices=['so400m', 'base224'], required=True)
    parser.add_argument('--ocr-url')
    parser.add_argument('--ocr-policy', choices=['all', 'rescue_only'], default='all')
    parser.add_argument('--route', choices=['standard', 'fullframe', 'owl640', 'softgate',
                                            'onnx640', 'onnx_dual', 'onnx_int8'], default='standard')
    parser.add_argument('--evidence-url')
    parser.add_argument('--evidence-cards', type=Path)
    parser.add_argument('--evidence-timeout', type=float, default=2.0)
    args = parser.parse_args()
    if args.threads < 1 or args.threads > 8:
        parser.error('--threads must be 1..8')
    if args.host != '127.0.0.1':
        parser.error('CPU test service must bind 127.0.0.1')
    if not .1 <= args.evidence_timeout <= 3:
        parser.error('--evidence-timeout must be 0.1..3 seconds')
    os.environ.setdefault('OMP_NUM_THREADS', str(args.threads))
    os.environ.setdefault('MKL_NUM_THREADS', str(args.threads))
    pipeline = CPUPipeline(args.catalog, args.index_dir, args.threads, args.encoder,
                           args.ocr_url, args.route, args.ocr_policy,
                           args.evidence_url, args.evidence_cards, args.evidence_timeout)

    Handler = make_handler(server.Handler, pipeline, args.threads)
    print(json.dumps({'ready': True, 'model_version': MODEL_VERSIONS[args.encoder] + '-' + args.route +
                      ('-ocr-' + args.ocr_policy if args.ocr_url else '') +
                      ('-evidence-v1' if args.evidence_url else ''),
                      'profile': pipeline.profile, 'cold_load_ms': pipeline.load_ms,
                      'host': args.host, 'port': args.port}), flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
