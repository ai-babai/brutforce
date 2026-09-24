"""Sigma CPU PaddleOCR on public organizer originals; no labels or catalog."""
import argparse
import hashlib
import os
import json
import time
from pathlib import Path
from PIL import Image
from paddleocr import PaddleOCR

ROOT = Path(os.environ.get('BRUTFORCE_AUDIT_ROOT', '/srv/lct/data/vision-retrieval/20260924/organizer-audit'))
MANIFEST = ROOT / 'queries-server.json'
OUT = ROOT / 'paddle-ocr.jsonl'


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',default=str(MANIFEST))
    ap.add_argument('--out',default=str(OUT))
    args=ap.parse_args()
    manifest_path=Path(args.manifest)
    out_path=Path(args.out)
    cases = json.loads(manifest_path.read_text())['cases']
    existing = {json.loads(s)['image_sha256'] for s in out_path.read_text().splitlines()} if out_path.exists() else set()
    ocr = PaddleOCR(device='cpu', cpu_threads=2, enable_mkldnn=False,
                    text_detection_model_name='PP-OCRv5_mobile_det',
                    text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',
                    text_det_limit_side_len=1280, text_det_limit_type='max',
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False)
    for case in cases:
        path = Path(case['path'])
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != case['sha256']:
            raise RuntimeError('hash mismatch '+case['case_id'])
        if sha in existing:
            continue
        start = time.monotonic()
        with Image.open(path) as im:
            im = im.convert('RGB')
            w,h = im.size
            im = im.crop((int(w*.20),int(h*.08),int(w*.80),int(h*.92)))
            im.thumbnail((1800,1800), Image.Resampling.LANCZOS)
            tmp = ROOT/'paddle-input.jpg'
            im.save(tmp,'JPEG',quality=90)
        try:
            result = list(ocr.predict(str(tmp)))
            obj = result[0].json['res'] if result else {}
            texts = [str(x) for x in obj.get('rec_texts',[])]
            scores = [float(x) for x in obj.get('rec_scores',[])]
            polys = [x.tolist() if hasattr(x,'tolist') else x for x in obj.get('rec_polys',[])]
            status,error = 'ok',None
        except Exception as exc:
            texts,scores,polys = [],[],[]
            status,error = 'error',f'{type(exc).__name__}: {exc}'
        ms = round((time.monotonic()-start)*1000)
        if status=='ok' and ms>8000:
            status='timeout'
        row={'case_id':case['case_id'],'image_sha256':sha,'status':status,'latency_ms':ms,
             'texts':texts,'scores':scores,'polys':polys,'error':error,
             'selection':'center_crop_60pct_width_84pct_height','source_set':case['source_set']}
        with out_path.open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n'); f.flush()
        print(case['case_id'],status,ms,len(texts),flush=True)

if __name__=='__main__':
    main()
