"""ORT6 SO400M whole+label visual branches, no routine OCR.

The target selector and whole embedding are exactly the ORT6 `onnx640` route.
For a selected target, the original OWLv2 label-context v2 crop is encoded
against the already-pinned SO400M label index; no references are rebuilt.
"""
from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image, ImageOps

from label_context_v2 import context_box
from onnx_so_pipeline import Pipeline as ORTPipeline
from ranking import top


class Pipeline(ORTPipeline):
    def __init__(self, catalog_path, index_dir, device):
        super().__init__(catalog_path, index_dir, device)
        index = np.load(index_dir / 'index.npz')
        self.label = index['label']
        if self.label.shape != self.full.shape:
            raise ValueError('SO400M full/label index shape mismatch')
        full_available = np.isfinite(self.full).all(axis=1)
        label_available = np.isfinite(self.label).all(axis=1)
        if not np.array_equal(full_available, label_available):
            raise ValueError('SO400M full/label availability mask mismatch')

    def predict(self, content, track):
        raw = super().predict(content, track)
        raw['branches_top20']['label'] = []
        raw['variants_top20']['label'] = []
        raw['architecture_version'] = 'rtdetr-so400m-onnx-whole-label-v1'
        box = raw['selection']['selected_box']
        if box is None:
            return raw
        started = time.perf_counter()
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        target = image if track == 'retrieval' else image.crop(box)
        standalone = raw['selection']['selection_reason'] == 'standalone_label_no_bottle'
        if standalone:
            label_choice = raw['label_selection']
            if label_choice is None:
                raise ValueError('standalone label selection missing')
            detected = None
        else:
            _, label_choice = self.model.label_region(target)
            raw['timings_ms']['label_detect_ms'] += label_choice['detect_ms']
            detected = label_choice['box']
        context = context_box(target.size, detected)
        label_crop = target.crop(context)
        step = time.perf_counter()
        feature = self.model.image_features([label_crop])[0]
        raw['timings_ms']['label_embedding_ms'] = round((time.perf_counter()-step)*1000)
        step = time.perf_counter()
        scores = np.where(np.isfinite(self.label).all(axis=1),
                          self.label @ feature, np.nan)
        ranking = top(scores, self.slugs)
        raw['timings_ms']['label_rank_ms'] = round((time.perf_counter()-step)*1000)
        raw['timings_ms']['dual_view_extra_ms'] = round((time.perf_counter()-started)*1000)
        raw['timings_ms']['total_ms'] += raw['timings_ms']['dual_view_extra_ms']
        raw['label_selection'] = label_choice
        raw['label_context_box'] = context
        raw['branches_top20']['label'] = ranking
        raw['variants_top20']['label'] = ranking
        return raw
