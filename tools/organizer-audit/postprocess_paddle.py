"""Apply the unchanged vision-baselines v1 matcher to organizer Paddle text."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision-baselines'))
from matcher import Matcher
from run import append

ROOT=Path('/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',default=str(ROOT/'paddle-ocr.jsonl'))
    ap.add_argument('--output',default=str(ROOT/'paddle-standalone.jsonl'))
    args=ap.parse_args()
    inp=Path(args.input);out=Path(args.output)
    existing={json.loads(s)['image_sha256'] for s in out.read_text().splitlines()} if out.exists() else set()
    matcher=Matcher()
    for line in inp.read_text().splitlines():
        x=json.loads(line)
        if x['image_sha256'] in existing: continue
        value='\n'.join(s for s,c in zip(x['texts'],x['scores']) if c>=.35)
        obj={'action':'wine' if value else 'unreadable','raw_text':value,'producer':'','wine_name':'','variety':'','vintage':''}
        ranked=matcher.rank(obj) if value else []
        pred={'slug':ranked[0]['slug']} if ranked and ranked[0]['score']>=.12 else {'action':'insufficient_information'}
        row={'case_id':x['case_id'],'image_sha256':x['image_sha256'],'track':'service',
             'model':'PaddleOCR 3.7.0 PP-OCRv5 mobile Sigma CPU','status':x['status'],
             'prediction':pred if x['status']=='ok' else None,'ocr':obj,'ranked':ranked,
             'latency_ms':x['latency_ms'],'total_latency_ms':x['latency_ms'],
             'selection':x['selection'],'error':x['error'],'source_set':x['source_set'],
             'matcher_version':'vision-baselines-v1','reuse':'fresh_original_image'}
        append(out,row)
        print(x['case_id'],x['status'],ranked[0]['slug'] if ranked else '-',flush=True)

if __name__=='__main__':main()
