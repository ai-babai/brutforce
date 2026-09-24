"""Run detector + whole-bottle/label visual retrieval on public, label-free queries."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from model import Vision,load_image,OWL_ID,OWL_REV,SIGLIP_ID,SIGLIP_REV
from index import find_image
from ranking import top
PREPROCESS_VERSION='owlv2-siglip2-labeldet-v1'
def cache_key(sha256,track):
    return (sha256,track,PREPROCESS_VERSION)

def append(path,row):
    with path.open('a') as f:
        f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--queries',type=Path,required=True);p.add_argument('--query-dir',type=Path)
    p.add_argument('--index-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--device',default='cuda');p.add_argument('--limit',type=int);p.add_argument('--case-id',action='append')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);(a.out/'crops').mkdir(exist_ok=True)
    query_raw=a.queries.read_bytes();query_hash=hashlib.sha256(query_raw).hexdigest()
    all_cases=json.loads(query_raw)['cases']
    cases=all_cases
    if a.case_id:cases=[x for x in cases if x['case_id'] in a.case_id]
    if a.limit is not None:cases=cases[:a.limit]
    data=np.load(a.index_dir/'index.npz');full=data['full'];label=data['label'];slugs=list(data['slugs'])
    if full.shape!=label.shape or full.shape[0]!=len(slugs):raise ValueError('index alignment')
    model=Vision(a.device)
    out=a.out/'visual.jsonl'
    prior=[json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
    case_map={x['case_id']:x for x in all_cases}
    for x in prior:
        case=case_map.get(x['case_id'])
        if (case is None or x['query_sha256']!=case['sha256'] or x['track']!=case['track']
            or x['query_manifest_sha256']!=query_hash
            or x.get('preprocess_version',PREPROCESS_VERSION)!=PREPROCESS_VERSION):
            raise ValueError('stale visual resume row '+x['case_id'])
    existing={x['case_id'] for x in prior}
    by_hash={cache_key(x['query_sha256'],x['track']):x for x in prior
             if not x.get('reused_from') and x.get('preprocess_version',PREPROCESS_VERSION)==PREPROCESS_VERSION}
    for case in cases:
        cid=case['case_id']
        if cid in existing:continue
        key=cache_key(case['sha256'],case['track'])
        if key in by_hash:
            source=by_hash[key]
            duplicate={**source,'case_id':cid,'track':case['track'],'reused_from':source['case_id'],
                       'query_manifest_sha256':query_hash}
            append(out,duplicate)
            print(json.dumps({'case_id':cid,'reused_from':source['case_id']}),flush=True)
            continue
        start=time.perf_counter();stage={}
        path=find_image(case,a.query_dir,cid)
        if path is None:raise FileNotFoundError(cid)
        image=load_image(path,case['sha256']);stage['load_ms']=round((time.perf_counter()-start)*1000)
        if case['track']=='service':
            target,selection=model.select_service(image)
            stage['detect_ms']=selection['detect_ms'];stage['class_ms']=selection['class_ms']
            standalone_label=None
            if target is None and selection['selection_reason']=='no_bottle_detected':
                region,standalone_label=model.label_region(image)
                if standalone_label['source'].startswith('owlv2') and standalone_label['score']>=.15:
                    target=region;selection['selected_box']=standalone_label['box']
                    selection['selection_reason']='standalone_label_no_bottle'
        else:
            target=image;selection={'boxes':[],'selected_box':[0,0,*image.size],'selection_reason':'verified_retrieval_crop'}
            stage['detect_ms']=0;stage['class_ms']=0
            standalone_label=None
        if target is None:
            ranked_full=[];ranked_label=[];crop_path=None;target_path=None
            label_choice=None;stage['label_detect_ms']=standalone_label['detect_ms'] if standalone_label else 0
            stage['save_ms']=0
            stage['whole_embedding_ms']=0;stage['label_embedding_ms']=0;stage['rank_ms']=0
        else:
            if standalone_label:
                label_crop=target;label_choice=standalone_label
            else:
                label_crop,label_choice=model.label_region(target)
            stage['label_detect_ms']=label_choice['detect_ms']
            t=time.perf_counter()
            target_path=a.out/'crops'/(cid+'-bottle.jpg');target.save(target_path,'JPEG',quality=92)
            crop_path=a.out/'crops'/(cid+'-label.jpg');label_crop.save(crop_path,'JPEG',quality=92)
            stage['save_ms']=round((time.perf_counter()-t)*1000)
            t=time.perf_counter();vfull=model.image_features([target])[0]
            stage['whole_embedding_ms']=round((time.perf_counter()-t)*1000)
            t=time.perf_counter();vlabel=model.image_features([label_crop])[0]
            stage['label_embedding_ms']=round((time.perf_counter()-t)*1000)
            t=time.perf_counter()
            whole_scores=np.where(np.isfinite(full).all(axis=1),full@vfull,np.nan)
            label_scores=np.where(np.isfinite(label).all(axis=1),label@vlabel,np.nan)
            ranked_full=top(whole_scores,slugs);ranked_label=top(label_scores,slugs)
            stage['rank_ms']=round((time.perf_counter()-t)*1000)
        stage['total_ms']=round((time.perf_counter()-start)*1000)
        row={'case_id':cid,'track':case['track'],'query_sha256':case['sha256'],
             'query_manifest_sha256':query_hash,'preprocess_version':PREPROCESS_VERSION,
             'selection':selection,'label_selection':label_choice,
             'target_path':str(target_path) if target_path else None,
             'label_crop_path':str(crop_path) if crop_path else None,
             'whole_top20':ranked_full,'label_top20':ranked_label,'timings_ms':stage,
             'models':{'detector':OWL_ID+'@'+OWL_REV,'shared_visual_encoder':SIGLIP_ID+'@'+SIGLIP_REV},
             'device':model.device,
             'index_info':str(a.index_dir/'index-info.json')}
        append(out,row)
        by_hash[key]=row
        print(json.dumps({'case_id':cid,'selection':selection['selection_reason'],'total_ms':stage['total_ms'],
                          'whole_top1':ranked_full[0]['slug'] if ranked_full else None,
                          'label_top1':ranked_label[0]['slug'] if ranked_label else None}),flush=True)
if __name__=='__main__':main()
