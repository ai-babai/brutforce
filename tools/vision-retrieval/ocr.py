"""Local PaddleOCR on the selected wine crop. Separate CPU process from GPU models."""
import argparse, json, time, hashlib
from pathlib import Path
from paddleocr import PaddleOCR

def read_rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--visual',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--limit',type=int)
    p.add_argument('--device',default='cpu')
    p.add_argument('--threads',type=int,default=2)
    args=p.parse_args();args.out.parent.mkdir(parents=True,exist_ok=True)
    rows=read_rows(args.visual);previous=read_rows(args.out) if args.out.exists() else []
    existing={x['case_id'] for x in previous};by_case={x['case_id']:x for x in previous}
    visual_by_case={x['case_id']:x for x in rows}
    for record in previous:
        visual=visual_by_case.get(record['case_id'])
        if visual is None:raise ValueError('stale OCR case '+record['case_id'])
        target=visual.get('target_path')
        digest=hashlib.sha256(Path(target).read_bytes()).hexdigest() if target else None
        if digest!=record.get('target_sha256'):
            raise ValueError('stale OCR target hash '+record['case_id'])
    t=time.perf_counter()
    kw=dict(device=args.device,text_detection_model_name='PP-OCRv5_mobile_det',
            text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',text_det_limit_side_len=1280,
            text_det_limit_type='max',use_doc_orientation_classify=False,
            use_doc_unwarping=False,use_textline_orientation=False)
    if args.device=='cpu':kw.update(cpu_threads=args.threads,enable_mkldnn=False)
    ocr=PaddleOCR(**kw)
    init_ms=round((time.perf_counter()-t)*1000)
    print(json.dumps({'ocr_init_ms':init_ms}),flush=True)
    pending=[x for x in rows if x['case_id'] not in existing]
    if args.limit is not None:pending=pending[:args.limit]
    for row in pending:
        cid=row['case_id'];start=time.perf_counter();path=row.get('target_path')
        if row.get('reused_from') and row['reused_from'] in by_case:
            record={**by_case[row['reused_from']],'case_id':cid,'reused_from':row['reused_from']}
        elif not path:
            record={'case_id':cid,'status':'no_wine_target','texts':[],'scores':[],'polys':[],
                    'ocr_ms':0,'target_sha256':None,'model':'PaddleOCR PP-OCRv5 mobile eslav'}
        else:
            pth=Path(path);digest=hashlib.sha256(pth.read_bytes()).hexdigest()
            try:
                result=list(ocr.predict(str(pth)))
                obj=result[0].json['res'] if result else {}
                record={'case_id':cid,'status':'ok','texts':[str(v) for v in obj.get('rec_texts',[])],
                        'scores':[float(v) for v in obj.get('rec_scores',[])],
                        'polys':[v.tolist() if hasattr(v,'tolist') else v for v in obj.get('rec_polys',[])],
                        'ocr_ms':round((time.perf_counter()-start)*1000),'target_sha256':digest,
                        'model':'PaddleOCR PP-OCRv5 mobile eslav'}
            except Exception as e:
                record={'case_id':cid,'status':'error','texts':[],'scores':[],'polys':[],
                        'ocr_ms':round((time.perf_counter()-start)*1000),'target_sha256':digest,
                        'error':type(e).__name__+': '+str(e)[:300],'model':'PaddleOCR PP-OCRv5 mobile eslav'}
        with args.out.open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n');f.flush()
        by_case[cid]=record
        print(json.dumps({'case_id':cid,'status':record['status'],'ocr_ms':record['ocr_ms'],
                          'text_count':len(record['texts'])}),flush=True)
if __name__=='__main__':main()
