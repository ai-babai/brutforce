"""Sigma-only PaddleOCR CPU extraction on sealed public images.

This module deliberately has no catalog, gold, or model-generated labels.
It records OCR text and boxes. The local postprocessor applies the same
fixed public-catalog matcher used for DeepSeek and Qwen.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from PIL import Image
from paddleocr import PaddleOCR


DATA = Path('/srv/lct/data/eval')
OUT = Path('/srv/lct/maks/vision-baselines/paddle-ocr.jsonl')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case-id', action='append')
    p.add_argument('--limit', type=int)
    args = p.parse_args()
    suite = json.loads((DATA / 'baskets/v1.json').read_text())
    ids = set(args.case_id or [])
    cases = [c for c in suite['cases'] if not ids or c['case_id'] in ids]
    if args.limit is not None:
        cases = cases[:args.limit]
    existing = {json.loads(line)['case_id'] for line in OUT.read_text().splitlines()} if OUT.exists() else set()
    started = time.monotonic()
    ocr = PaddleOCR(device='cpu', cpu_threads=2, enable_mkldnn=False, text_detection_model_name='PP-OCRv5_mobile_det', text_recognition_model_name='eslav_PP-OCRv5_mobile_rec', text_det_limit_side_len=1280, text_det_limit_type='max', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    print('init_ms', round((time.monotonic()-started)*1000), flush=True)
    for case in cases:
        cid = case['case_id']
        if cid in existing:
            continue
        t = time.monotonic()
        path = DATA / case['image_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != case['image_sha256']:
            raise RuntimeError(f'Sealed image hash mismatch: {cid}')
        with Image.open(path) as im:
            im = im.convert('RGB')
            if case['tracks'][0] == 'service':
                w, h = im.size
                # Geometry-only target approximation. It can miss a side wine.
                im = im.crop((int(w*.20), int(h*.08), int(w*.80), int(h*.92)))
            im.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            tmp = Path('/srv/lct/maks/vision-baselines/input.jpg')
            im.save(tmp, 'JPEG', quality=90)
        try:
            result = list(ocr.predict(str(tmp)))
            obj = result[0].json['res'] if result else {}
            texts = [str(x) for x in obj.get('rec_texts', [])]
            scores = [float(x) for x in obj.get('rec_scores', [])]
            polys = [x.tolist() if hasattr(x, 'tolist') else x for x in obj.get('rec_polys', [])]
            status = 'ok'
            error = None
        except Exception as e:
            status = 'error'
            texts, scores, polys = [], [], []
            error = f'{type(e).__name__}: {e}'
        ms = round((time.monotonic()-t)*1000)
        if status == 'ok' and ms > 8000:
            status = 'timeout'
        row = {'case_id': cid, 'track': case['tracks'][0], 'status': status, 'latency_ms': ms, 'texts': texts, 'scores': scores, 'polys': polys, 'error': error, 'selection': 'center_crop_60pct_width_84pct_height' if case['tracks'][0] == 'service' else 'verified_crop_full', 'suite_hash': suite['suite_hash']}
        with OUT.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
        print(cid, status, ms, len(texts), flush=True)


if __name__ == '__main__':
    main()
