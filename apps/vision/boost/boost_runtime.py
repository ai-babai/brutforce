"""Optional simple84 retrieval. Uses existing Batch32, RTDETR and original index."""
import hashlib
import io
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='boost-detector')
_DETECT_LOCK = threading.Lock()

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read_boost(cfg, binding):
    flag = cfg.get('boost', 0)
    if type(flag) is not int or flag not in (0, 1):
        raise ValueError('config.json: boost должен быть 0 или 1')
    if not flag:
        return None
    pin = binding['boost']; path = Path(pin['manifest_path'])
    if sha(path) != pin['manifest_sha256']:
        raise ValueError('Boost policy manifest mismatch')
    manifest = json.loads(path.read_text())
    roles = {p['role']: p['sha256'] for p in binding['files']}
    if (manifest['model_id'] != cfg['model_id'] or
        manifest['checkpoint_sha256'] != binding['checkpoint_sha256'] or
        manifest['base_index_sha256'] != roles['index'] or
        manifest['onnx_external_weights_sha256'] != roles['onnx_external_weights']):
        raise ValueError('Boost policy model mismatch')
    for name, expected in manifest['code_sha256'].items():
        if sha(path.parent / name) != expected:
            raise ValueError('Boost code mismatch: ' + name)
    from boost_policy import CASCADE_SIMPLE84, EXECUTION
    if manifest['policy'] != CASCADE_SIMPLE84 or manifest['execution'] != EXECUTION:
        raise ValueError('Unknown or modified simple84 policy')
    source = manifest['gallery_sources']['legacy_label']
    if sha(source['path']) != source['sha256']:
        raise ValueError('Boost legacy gallery mismatch')
    manifest['policy'] = dict(manifest['policy'], gallery_sources=manifest['gallery_sources'])
    return manifest

def _detect(model, image):
    step = time.perf_counter()
    with _DETECT_LOCK:
        boxes, _ = model.detect(image)
    return boxes, round(1000 * (time.perf_counter() - step))

def _consume_background(future):
    if not future.cancelled() and future.exception() is not None:
        logging.getLogger(__name__).debug('Unused detector job failed: %s',
                                         type(future.exception()).__name__)

def view_box(image, central, view):
    if view == 'fullframe':
        return [0, 0, *image.size]
    if view not in ('central_pad10', 'central_pad25'):
        raise ValueError('Unsupported simple84 view')
    x1, y1, x2, y2 = central
    padding = .10 if view == 'central_pad10' else .25
    bw, bh = x2 - x1, y2 - y1
    x1, y1, x2, y2 = x1-padding*bw, y1-padding*bh, x2+padding*bw, y2+padding*bh
    x1 = max(0, min(image.width-1, math.floor(x1)))
    y1 = max(0, min(image.height-1, math.floor(y1)))
    return [x1, y1, max(x1+1, min(image.width, math.ceil(x2))),
            max(y1+1, min(image.height, math.ceil(y2)))]

def predict(engine, content, policy, catalog_version, index_version):
    import numpy as np
    from PIL import Image, ImageOps
    from boost_policy import cascade84, needs_crops
    started = time.perf_counter()
    with Image.open(io.BytesIO(content)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    stage = dict.fromkeys(['decode_ms', 'detect_ms', 'class_ms', 'label_detect_ms',
                          'whole_embedding_ms', 'label_embedding_ms', 'ocr_ms',
                          'rank_ms', 'fusion_ms'], 0)
    stage['decode_ms'] = round(1000 * (time.perf_counter() - started))
    detector = _POOL.submit(_detect, engine.model, image.copy())
    detector.add_done_callback(_consume_background)
    finite = np.isfinite(engine.full).all(axis=1)
    features, crops, scores = {}, {}, {}
    def encode(view, box):
        crops[view] = box; key = tuple(box); step = time.perf_counter()
        if key not in features:
            target = image if view == 'fullframe' else image.crop(box)
            features[key] = engine.model.image_features([target])[0]
        stage['whole_embedding_ms'] += round(1000 * (time.perf_counter() - step))
        step = time.perf_counter()
        scores[view] = np.where(finite, engine.full @ features[key], np.nan)
        stage['rank_ms'] += round(1000 * (time.perf_counter() - step))
        return features[key]
    encode('fullframe', [0, 0, *image.size])
    final_scores = scores['fullframe']; boxes = []
    crop_needed = needs_crops(final_scores)
    if crop_needed:
        boxes, stage['detect_ms'] = detector.result()
        central = [0, 0, *image.size]
        for box in boxes:
            x1, y1, x2, y2 = box['box']
            box['center_distance'] = round(math.hypot(
                (x1+x2)/(2*image.width)-.5, (y1+y2)/(2*image.height)-.5), 5)
        if boxes:
            central = min(boxes, key=lambda b: (b['center_distance'], -b['score']))['box']
        encode('central_pad25', view_box(image, central, 'central_pad25'))
        pad10 = encode('central_pad10', view_box(image, central, 'central_pad10'))
        step = time.perf_counter(); source = policy['gallery_sources']['legacy_label']
        key = (source['sha256'], tuple(engine.slugs))
        if getattr(engine, '_boost_gallery_key', None) != key:
            with np.load(source['path'], allow_pickle=False) as index:
                slugs = list(index['slugs'])
                if list(engine.slugs[:len(slugs)]) != slugs:
                    raise ValueError('Boost legacy slug order mismatch')
                gallery = np.full(engine.full.shape, np.nan, dtype=np.float32)
                gallery[:len(slugs)] = index['label']
            engine._boost_label_gallery, engine._boost_gallery_key = gallery, key
        gallery = engine._boost_label_gallery
        legacy_scores = np.where(np.isfinite(gallery).all(axis=1), gallery @ pad10, np.nan)
        final_scores = cascade84(scores['fullframe'], scores['central_pad25'], legacy_scores)
        stage['fusion_ms'] = round(1000 * (time.perf_counter() - step))
    else:
        detector.cancel()
    step = time.perf_counter()
    ranked = [engine.slugs[int(i)] for i in np.argsort(-final_scores)
              if np.isfinite(final_scores[int(i)])][:20]
    stage['rank_ms'] += round(1000 * (time.perf_counter() - step))
    stage['total_ms'] = round(1000 * (time.perf_counter() - started))
    result = dict(catalog_version=catalog_version, index_version=index_version,
                  ranked_slugs=ranked, timings_ms=stage, track='retrieval',
                  image_sha256=hashlib.sha256(content).hexdigest(),
                  boost=dict(policy=policy['name'], boxes=crops,
                             conditional_fullframe=not crop_needed,
                             detector_fallback=crop_needed and not boxes))
    if ranked:
        result['slug'] = ranked[0]
    else:
        result['action'] = 'insufficient_information'
    return result
