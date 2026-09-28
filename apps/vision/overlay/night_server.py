"""One new conditional OCR rescue branch around immutable F0 HTTP pipeline."""

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


parent_dir = Path(os.environ['F0_BASE_CODE_DIR']).resolve(strict=True)
parent = parent_dir / 'night_server.py'
assert hashlib.file_digest(parent.open('rb'), 'sha256').hexdigest() == (
    'bc9684760dc9dae4c376e1de988420546f343a7b8366039a227cd32a8c044eef')
# Absolute script launches otherwise import modules from their own directory.
sys.path.insert(0, str(parent_dir))
spec = importlib.util.spec_from_file_location('f0_immutable_night_server', parent)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

lexicon_path = Path(os.environ['F8_OCR_LEXICON_SPEC'])
assert hashlib.file_digest(lexicon_path.open('rb'), 'sha256').hexdigest() == (
    '1cbf9d3436e2e58b116ef030557b070f260176aa6e2a4beae919c567852b4204')
lexicon = json.loads(lexicon_path.read_text())
WINE = re.compile(lexicon['fixed_positive_regex'], re.IGNORECASE)
NONWINE = re.compile(lexicon['fixed_nonwine_veto_regex'], re.IGNORECASE)
VERSION = 'F8-CPU-text-confirmed-rescue-P4-diagnostic-v1'
base.MODEL_VERSIONS['so400m'] += '-f8-text-confirmed-v1'
PARENT_MODULE_SHAS = {
    'onnx_so_pipeline': '0d8f2fa748b1fdfaaf6d5ac334d238e0bb526ecb22c6739414b35433997cec60',
    'fast_owl_pipeline': '446cade2801512d9f2f8902ffec7aacc18997d0cc26af815101d93b75e32a992',
    'whole_encoder_server': 'ced09edc8bcd37656314948a40b3a423c18d3175f66e5ffa01c3e3b058c7d79f',
    'detector_encoder_server': '78d68a455d8f558002eb0d3305d3dd41dce84a70095415109727feeb36f32368',
    'model': 'e281c0f66980c0cb2b8c40bddc739b8be8a08204f8f809bbc4588995e7f1582e',
    'ranking': '8f4277326d0c16154f2bcb4ad572df5cdab47fa62273a44900fc603f08082e49',
    'server': 'ed326b24c939cac71ed6e878ce301fd0146f98563a3db89b9b11b9cbad526405',
}


def module_proof(name):
    module = sys.modules[name]
    source = Path(module.__file__).resolve(strict=True)
    if source.parent != parent_dir:
        raise RuntimeError(f'wrong F0 import path: {name}: {source}')
    sha = hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()
    if sha != PARENT_MODULE_SHAS[name]:
        raise RuntimeError(f'wrong F0 source hash: {name}: {sha}')
    return {'path': str(source), 'sha256': sha}


class CPUPipeline(base.CPUPipeline):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.route != 'onnx640' or self.encoder != 'so400m' or self.ocr_url:
            raise ValueError('F8 is pinned to F0 SO400M onnx640 without external OCR')
        importlib.import_module('ranking')
        print(json.dumps({'kind': 'f8_same_interpreter_import_proof', 'candidate_id': VERSION,
                          'parent': str(parent), 'parent_sha256':
                          hashlib.file_digest(parent.open('rb'), 'sha256').hexdigest(),
                          'modules': {name: module_proof(name)
                                      for name in PARENT_MODULE_SHAS}}), flush=True)
        original = self.engine.predict

        def predict(content, track):
            raw = original(content, track)
            if track == 'service' and raw['selection']['selection_reason'] == 'detected_bottles_classified_nonwine':
                self._text_rescue(content, raw)
            return raw

        self.engine.predict = predict

    def _text_rescue(self, content, raw):
        started = time.perf_counter()
        candidates = [item for item in raw['selection']['boxes']
                      if -.030 <= item.get('wine_margin', float('-inf')) < -.015]
        if not candidates:
            return
        candidate = min(candidates, key=lambda item: (
            item['center_distance'], -item['wine_margin']))
        selection = raw['selection']
        selection['f8_candidate_count'] = len(candidates)
        selection['f8_margin'] = candidate['wine_margin']
        decision = 'no_confident_label'
        ocr_ms = 0
        label_ms = 0
        try:
            with Image.open(io.BytesIO(content)) as opened:
                image = ImageOps.exif_transpose(opened).convert('RGB')
            target = image.crop(candidate['box'])
            label, details = self.engine.model.label_region(target)
            label_ms = details['detect_ms']
            if not details['source'].startswith('owlv2_label') or (details['score'] or 0) < .15:
                return
            label.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            picture = io.BytesIO()
            label.save(picture, format='PNG')
            step = time.perf_counter()
            try:
                run = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'rus+eng',
                                      '--psm', '6'], input=picture.getvalue(),
                                     capture_output=True, timeout=2.5, check=False,
                                     env={**os.environ, 'OMP_THREAD_LIMIT':'1'})
                ocr_ms = round((time.perf_counter() - step)*1000)
            except subprocess.TimeoutExpired:
                decision = 'ocr_timeout_fail_closed'
                return
            if run.returncode != 0:
                decision = 'ocr_error_fail_closed'
                return
            text = unicodedata.normalize('NFKC', run.stdout.decode('utf-8','replace')).casefold()
            wine = WINE.search(text)
            veto = NONWINE.search(text)
            if veto or not wine:
                decision = 'nonwine_veto' if veto else 'no_wine_text'
                return
            step = time.perf_counter()
            from ranking import top
            feature = self.engine.model.image_features([target])[0]
            scores = np.where(np.isfinite(self.engine.full).all(axis=1),
                              self.engine.full @ feature, np.nan)
            ranks = top(scores, self.engine.slugs)
            if not ranks:
                decision = 'no_catalog_rank_fail_closed'
                return
            # No parent answer is changed until all recognition and ranking succeeds.
            raw['branches_top20']['whole'] = ranks
            selection['selected_box'] = candidate['box']
            selection['selection_reason'] = 'f8_text_confirmed_rescue'
            raw.pop('action', None)
            raw['slug'] = ranks[0]['slug']
            raw['timings_ms']['whole_embedding_ms'] = round((time.perf_counter()-step)*1000)
            raw['timings_ms']['rank_ms'] = 0
            decision = 'accepted'
        except Exception as exc:
            decision = 'rescue_exception_fail_closed_' + type(exc).__name__
        finally:
            raw['timings_ms']['label_detect_ms'] = label_ms
            raw['timings_ms']['ocr_ms'] = ocr_ms
            raw['timings_ms']['total_ms'] += round((time.perf_counter()-started)*1000)
            selection['f8_decision'] = decision
            print(json.dumps({'kind':'f8_rescue_public_input',
                              'query_sha256':hashlib.sha256(content).hexdigest(),
                              'decision':decision,
                              'duration_ms':round((time.perf_counter()-started)*1000),
                              'ocr_ms':ocr_ms}),flush=True)


base.CPUPipeline = CPUPipeline

if __name__ == '__main__':
    print(json.dumps({'candidate_id': VERSION,
                      'overlay_module': __file__,
                      'parent_source_sha256': hashlib.file_digest(parent.open('rb'),'sha256').hexdigest(),
                      'lexicon_spec_sha256': hashlib.file_digest(lexicon_path.open('rb'),'sha256').hexdigest()}),
          flush=True)
    base.main()
