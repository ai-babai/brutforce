"""Reject weak composite bottle boxes before the unchanged wine/center selection.

Development hypothesis C, declared 2026-09-25 after inspecting localization traces.
No image identity, catalog, OCR, private labels, or learned parameters are used.
"""
from __future__ import annotations

import math

VERSION = 'composite-box-guard-v1'
MIN_CHILD_SCORE = 0.50
MIN_SCORE_RATIO = 2.0
MIN_CONTAINMENT = 0.90
MAX_CHILD_IOU = 0.20


def _area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _intersection(a, b):
    return _area([max(a[0], b[0]), max(a[1], b[1]),
                  min(a[2], b[2]), min(a[3], b[3])])


def filter_composite_candidates(candidates: list[dict], image_size: tuple[int, int]):
    """Return retained input records and an auditable list of suppressed records.

    A box is suppressed only if it contains >=90% of each of TWO separate
    confident boxes: each score >=.5 and >=2x the parent's, pairwise IoU <=.2.
    A single strong child, overlapping duplicate boxes, or weak children do
    not qualify. No global score/aspect-ratio filter is added. Input unchanged.
    """
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError('positive image size required')
    for record in candidates:
        box = record.get('box', [])
        score = record.get('score')
        if (len(box) != 4 or not all(math.isfinite(float(x)) for x in box)
                or _area(box) <= 0 or not isinstance(score, (int, float))
                or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('invalid detector candidate')
    retained, removed = [], []
    for parent_index, parent in enumerate(candidates):
        children = []
        for child_index, child in enumerate(candidates):
            if child_index == parent_index:
                continue
            if child['score'] < max(MIN_CHILD_SCORE, MIN_SCORE_RATIO * parent['score']):
                continue
            overlap = _intersection(parent['box'], child['box']) / _area(child['box'])
            if overlap >= MIN_CONTAINMENT:
                children.append((child_index, child))
        evidence = None
        for offset, (left_index, left) in enumerate(children):
            for right_index, right in children[offset + 1:]:
                intersection = _intersection(left['box'], right['box'])
                union = _area(left['box']) + _area(right['box']) - intersection
                if intersection / union <= MAX_CHILD_IOU:
                    evidence = [left_index, right_index]
                    break
            if evidence is not None:
                break
        if evidence is None:
            retained.append(parent)
        else:
            removed.append({'candidate_index': parent_index, 'box': list(parent['box']),
                            'score': parent['score'], 'child_indices': evidence,
                            'reason': 'weak_box_contains_two_separate_confident_bottles',
                            'version': VERSION})
    return retained, removed
