"""One target-scoped OCR decision, shared by in-process and forwarding routes."""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.error
import urllib.request

from PIL import Image, ImageOps

from grape_normalization import GrapeNormalizedFieldMatcher


class EvidenceProcessor:
    def __init__(self, cards: dict, slugs: list[str], ocr_url: str, timeout: float):
        self.matcher = GrapeNormalizedFieldMatcher(cards, slugs)
        self.ocr_url = ocr_url
        self.timeout = timeout

    def rerank(self, content: bytes, selection: dict, ranks: list[dict], track: str,
               base_ms: int):
        started = time.perf_counter()
        positions = self.matcher.eligible_positions(ranks)
        diag = {'state': 'not_eligible', 'before': [x['slug'] for x in ranks],
                'after': [x['slug'] for x in ranks], 'field_positions_1based':
                [i + 1 for i in positions], 'target_box': selection['selected_box'],
                'target_sha256': None, 'ocr_error': None, 'ocr_texts': [], 'ocr_scores': [],
                'worker_ocr_ms': None, 'candidate_evidence': [], 'observations': [],
                'base_ms': base_ms, 'product_budget_ms': 8500, 'reserve_ms': 350,
                'ocr_timeout_ms': None}
        if selection['selected_box'] is None:
            diag['state'] = 'no_selected_target'
            return ranks, diag, round((time.perf_counter()-started)*1000)
        if not positions:
            return ranks, diag, round((time.perf_counter()-started)*1000)
        if base_ms >= 7900:
            diag['state'] = 'budget_exhausted'
            return ranks, diag, round((time.perf_counter()-started)*1000)

        box = selection['selected_box']
        # An overlapping detector box may be a second physical bottle; do not
        # assign its writing to the selected target without a separate polygon.
        if track == 'service':
            area = max(1, (box[2]-box[0]) * (box[3]-box[1]))
            for other in selection['boxes']:
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
            remaining_ms = 8500 - 350 - base_ms - round((time.perf_counter()-started)*1000)
            if remaining_ms <= 250:
                diag['state'] = 'budget_exhausted'
                return ranks, diag, round((time.perf_counter()-started)*1000)
            timeout = min(self.timeout, remaining_ms / 1000)
            diag['ocr_timeout_ms'] = round(timeout * 1000)
            request = urllib.request.Request(self.ocr_url.rstrip('/') + '/ocr',
                data=data, method='POST', headers={'Content-Type': 'image/jpeg'})
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
        except urllib.error.HTTPError as exc:
            try:
                worker_error = json.load(exc).get('error', '')
            except (ValueError, OSError):
                worker_error = ''
            diag['state'] = 'ocr_failed'
            diag['ocr_error'] = f'HTTP {exc.code}: {str(worker_error)[:200]}'
        except Exception as exc:
            diag['state'] = 'ocr_failed'
            diag['ocr_error'] = type(exc).__name__ + ': ' + str(exc)[:200]
        return ranks, diag, round((time.perf_counter()-started)*1000)
