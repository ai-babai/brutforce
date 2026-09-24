"""Pretrained detector swaps for the frozen v2 retrieval composition.

No labels or evaluation answers are read here. YOLO26n's COCO ``bottle`` box
still has to pass the existing SigLIP wine classifier before target selection.
"""
from __future__ import annotations

import math
import time

from model import (
    CLASS_PROMPTS, DETECT_PROMPTS, LABEL_PROMPTS, OWL_ID, OWL_REV,
    SIGLIP_ID, SIGLIP_REV, Vision, clamp_box, iou,
)

YOLOE_WEIGHTS = 'yoloe-26s-seg.pt'
YOLO26_WEIGHTS = 'yolo26n.pt'
YOLOE_BOTTLE_CLASSES = [
    'a wine bottle', 'a glass bottle of wine', 'a beer bottle',
    'a bottle of liquor', 'a milk bottle', 'a carton of milk',
    'a product bottle',
]
YOLOE_LABEL_CLASSES = [
    'a wine label on a bottle',
    'a rectangular product label with wine text', 'a printed wine bottle label',
]
GEOMETRIC_LABEL_MODE = 'yolo26n-geometric-label-query-v1'
RTDETR_ID = 'PekingU/rtdetr_r18vd'
RTDETR_REV = 'ac77a11ff0170a41b771c03264987f8ce2b0d753'


class DetectorVision(Vision):
    def __init__(self, device='cuda', variant='yoloe26s'):
        if variant not in ('yoloe26s', 'yoloe26s-strict', 'yolo26n',
                           'yolo26n-geometric', 'rtdetr-r18'):
            raise ValueError('unknown detector variant: '+variant)
        self.variant = variant
        if variant in ('yolo26n', 'rtdetr-r18'):
            # This controlled swap retains the original OWLv2 label pass.
            super().__init__(device)
        else:
            import torch
            from transformers import AutoProcessor, AutoModel
            self.torch = torch
            self.device = device if device != 'cuda' or torch.cuda.is_available() else 'cpu'
            self.embed_processor = AutoProcessor.from_pretrained(SIGLIP_ID, revision=SIGLIP_REV)
            self.embedder = AutoModel.from_pretrained(
                SIGLIP_ID, revision=SIGLIP_REV, use_safetensors=True
            ).to(self.device).eval()
            self.class_features = self.text_features(CLASS_PROMPTS)
        if variant.startswith('yoloe26s'):
            from ultralytics import YOLOE
            # Separate prompt heads avoid a label class suppressing a bottle
            # class on the same region. Both text embeddings are built once.
            self.yolo_bottle = YOLOE(YOLOE_WEIGHTS)
            self.yolo_bottle.set_classes(YOLOE_BOTTLE_CLASSES)
            self.yolo_bottle.to(self.device)
            self.yolo_label = YOLOE(YOLOE_WEIGHTS)
            self.yolo_label.set_classes(YOLOE_LABEL_CLASSES)
            self.yolo_label.to(self.device)
        elif variant.startswith('yolo26n'):
            from ultralytics import YOLO
            self.yolo = YOLO(YOLO26_WEIGHTS)
            self.bottle_class = next(
                int(k) for k, name in self.yolo.names.items() if name == 'bottle'
            )
            self.yolo.to(self.device)
        else:
            from transformers import AutoImageProcessor, AutoModelForObjectDetection
            self.rtdetr_processor = AutoImageProcessor.from_pretrained(
                RTDETR_ID, revision=RTDETR_REV,
            )
            self.rtdetr = AutoModelForObjectDetection.from_pretrained(
                RTDETR_ID, revision=RTDETR_REV, use_safetensors=True,
            ).to(self.device).eval()
            self.bottle_class = next(
                int(k) for k, name in self.rtdetr.config.id2label.items()
                if name.lower() == 'bottle'
            )

    def _rtdetr_boxes(self, image, threshold):
        start = time.perf_counter()
        inputs = self.rtdetr_processor(images=image, return_tensors='pt').to(self.device)
        with self.torch.inference_mode():
            outputs = self.rtdetr(**inputs)
        self._sync()
        result = self.rtdetr_processor.post_process_object_detection(
            outputs, target_sizes=self.torch.tensor([image.size[::-1]]),
            threshold=threshold,
        )[0]
        raw = []
        for box, score, cls in zip(result['boxes'], result['scores'], result['labels']):
            if int(cls) != self.bottle_class:
                continue
            raw.append({'box': clamp_box(box.tolist(), image.size),
                        'score': float(score), 'prompt': 'a product bottle'})
        raw.sort(key=lambda x: x['score'], reverse=True)
        distinct = []
        for item in raw:
            if all(iou(item['box'], prior['box']) < .65 for prior in distinct):
                distinct.append(item)
        return distinct[:12], round((time.perf_counter()-start)*1000)

    def _yolo_boxes(self, image, *, label=False):
        start = time.perf_counter()
        detector = (self.yolo_label if label else self.yolo_bottle) if self.variant.startswith('yoloe26s') else self.yolo
        result = detector.predict(
            source=image, imgsz=640, conf=.06 if label else .08,
            max_det=100, verbose=False, device=self.device,
        )[0]
        self._sync()
        raw = []
        for box, score, cls in zip(
            result.boxes.xyxy.tolist(), result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
        ):
            idx = int(cls)
            if self.variant.startswith('yoloe26s'):
                prompt = (YOLOE_LABEL_CLASSES if label else YOLOE_BOTTLE_CLASSES)[idx]
            else:
                if idx != self.bottle_class or label:
                    continue
                prompt = 'a product bottle'
            raw.append({
                'box': clamp_box(box, image.size), 'score': float(score),
                'prompt': prompt,
            })
        raw.sort(key=lambda x: x['score'], reverse=True)
        distinct = []
        for item in raw:
            if all(iou(item['box'], prior['box']) < .65 for prior in distinct):
                distinct.append(item)
        return distinct[:12], round((time.perf_counter()-start)*1000)

    def detect(self, image, threshold=.08):
        if self.variant == 'rtdetr-r18':
            return self._rtdetr_boxes(image, threshold)
        return self._yolo_boxes(image)

    def select_service(self, image):
        if self.variant != 'yoloe26s-strict':
            return super().select_service(image)
        # Development ablation: keep the original fixed SigLIP wine margin,
        # but do not let a YOLOE text prompt bypass it.
        started = time.perf_counter()
        candidates, detect_ms = self.detect(image)
        if not candidates:
            return None, {'boxes': [], 'selected_box': None,
                          'selection_reason': 'no_bottle_detected',
                          'detect_ms': detect_ms, 'class_ms': 0}
        features = self.image_features([image.crop(x['box']) for x in candidates])
        semantic = features@self.class_features.T
        w, h = image.size
        for candidate, sim in zip(candidates, semantic):
            candidate['wine_margin'] = round(float(sim[0]-max(sim[1:])), 5)
            cx = (candidate['box'][0]+candidate['box'][2])/(2*w)
            cy = (candidate['box'][1]+candidate['box'][3])/(2*h)
            candidate['center_distance'] = round(math.hypot(cx-.5, cy-.5), 5)
        wine = [candidate for candidate in candidates if candidate['wine_margin'] >= -.015]
        if not wine:
            return None, {'boxes': candidates, 'selected_box': None,
                          'selection_reason': 'detected_bottles_classified_nonwine',
                          'detect_ms': detect_ms,
                          'class_ms': round((time.perf_counter()-started)*1000)-detect_ms}
        chosen = min(wine, key=lambda c: (c['center_distance'], -c['wine_margin']))
        return image.crop(chosen['box']), {'boxes': candidates,
            'selected_box': chosen['box'],
            'selection_reason': 'nearest_center_wine_strict',
            'detect_ms': detect_ms,
            'class_ms': round((time.perf_counter()-started)*1000)-detect_ms}

    def label_region(self, image):
        if self.variant in ('yolo26n', 'rtdetr-r18'):
            return super().label_region(image)
        w, h = image.size
        if self.variant == 'yolo26n-geometric':
            box = clamp_box((w*.06, h*.30, w*.94, h*.92), image.size)
            return image.crop(box), {
                'source': GEOMETRIC_LABEL_MODE, 'box': box,
                'score': None, 'detect_ms': 0, 'candidates': [],
            }
        candidates, ms = self._yolo_boxes(image, label=True)
        eligible, large = [], []
        for item in candidates:
            box = item['box']
            area = (box[2]-box[0])*(box[3]-box[1])/(w*h)
            if area < .008:
                continue
            cx = (box[0]+box[2])/(2*w)
            cy = (box[1]+box[3])/(2*h)
            key = (math.hypot(cx-.5, cy-.62)-.35*item['score'], item)
            (eligible if area <= .65 else large).append(key)
        if eligible or (large and h/w <= 2.2):
            selected = min(eligible or large, key=lambda v: v[0])[1]
            return image.crop(selected['box']), {
                'source': 'yoloe26s_label', 'box': selected['box'],
                'score': selected['score'], 'detect_ms': ms,
                'candidates': candidates,
            }
        box = clamp_box((w*.06, h*.30, w*.94, h*.84), image.size)
        return image.crop(box), {
            'source': 'heuristic_band_fallback', 'box': box,
            'score': None, 'detect_ms': ms, 'candidates': candidates,
        }


def make_vision(variant, device='cuda'):
    return DetectorVision(device=device, variant=variant)
