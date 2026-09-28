"""Score independent whole, label, OCR and fixed fusion branches from cached inference."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from ranking import Lexical,top

WEIGHTS={'whole':.25,'label':.35,'ocr':.40}
VARIANTS={'whole':('whole',),'label':('label',),'ocr':('ocr',),
          'whole_label':('whole','label'),'whole_ocr':('whole','ocr'),
          'label_ocr':('label','ocr'),'all':('whole','label','ocr')}
def read_rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def ocr_top(matcher,text,slugs):
    if len(text.strip())<4:return []
    scores=matcher.scores(text)
    return top(scores,slugs) if float(np.max(scores))>0 else []
def assert_target_hash(visual,ocr):
    target=visual.get('target_path')
    digest=hashlib.sha256(Path(target).read_bytes()).hexdigest() if target else None
    if ocr and ocr.get('target_sha256')!=digest:
        raise ValueError('OCR target hash differs from visual crop: '+visual['case_id'])
def rank_fuse(branches):
    out={}
    usable={k:v for k,v in branches.items() if v}
    denominator=sum(WEIGHTS[k] for k in usable) or 1
    for name,entries in usable.items():
        for rank,item in enumerate(entries,1):
            slug=item['slug']
            out[slug]=out.get(slug,0)+WEIGHTS[name]/denominator/(60+rank)
    return [{'slug':s,'score':round(float(v),7)} for s,v in sorted(out.items(),key=lambda x:(-x[1],x[0]))[:20]]
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--catalog',type=Path,required=True);p.add_argument('--visual',type=Path,required=True)
    p.add_argument('--ocr',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    catalog=json.loads(args.catalog.read_text())['references'];slugs=[r['slug'] for r in catalog]
    matcher=Lexical([{'slug':r['slug'],'title':r.get('title',''),'producer':r.get('winery','')} for r in catalog])
    ocr={x['case_id']:x for x in read_rows(args.ocr)}
    output=[]
    for vis in read_rows(args.visual):
        start=time.perf_counter();cid=vis['case_id'];raw=ocr.get(cid,{})
        assert_target_hash(vis,raw)
        text='\n'.join(t for t,s in zip(raw.get('texts',[]),raw.get('scores',[])) if float(s)>=.35)
        lexical=ocr_top(matcher,text,slugs)
        branches={'whole':vis['whole_top20'],'label':vis['label_top20'],'ocr':lexical}
        variants={name:rank_fuse({key:branches[key] for key in subset}) for name,subset in VARIANTS.items()}
        fused=variants['all']
        no_target=vis['track']=='service' and vis['selection']['selected_box'] is None
        predictions={name:({'action':'no_match'} if no_target else {'slug':ranking[0]['slug']} if ranking else {'action':'insufficient_information'})
                     for name,ranking in variants.items()}
        predicted=predictions['all']
        ocr_ms=raw.get('ocr_ms',0)
        merge_ms=round((time.perf_counter()-start)*1000)
        total_ms=vis['timings_ms']['total_ms']+ocr_ms+merge_ms
        stage=vis['timings_ms']
        common=stage.get('load_ms',0)+stage.get('detect_ms',0)+stage.get('class_ms',0)
        if vis['selection']['selection_reason']=='standalone_label_no_bottle':
            common+=stage.get('label_detect_ms',0)
        variant_estimated_ms={}
        for name,subset in VARIANTS.items():
            estimate=common+merge_ms
            if 'whole' in subset:estimate+=stage.get('whole_embedding_ms',0)+stage.get('rank_ms',0)
            if 'label' in subset:estimate+=stage.get('label_detect_ms',0)+stage.get('label_embedding_ms',0)
            if 'ocr' in subset:estimate+=ocr_ms
            variant_estimated_ms[name]=estimate
        row={'case_id':cid,'track':vis['track'],'status':'ok','diagnostic_batch_over_10s':total_ms>10000,
             'prediction':predicted,'predictions':predictions,'branches':branches,
             'variants_top20':variants,'fused_top20':fused,'ocr_text':text,
             'timings_ms':{**vis['timings_ms'],'ocr_ms':ocr_ms,'merge_ms':merge_ms,'sequential_total_ms':total_ms},
             'variant_cached_stage_sum_ms':variant_estimated_ms,
             'variant_latency_note':'Cached stage sums exclude diagnostic crop saving and HTTP; quality ablations are not live deadline measurements.',
             'ocr_status':raw.get('status','missing'),'selection':vis['selection'],
             'label_selection':vis.get('label_selection'),
             'label_context_box':vis.get('label_context_box'),
             'query_sha256':vis['query_sha256'],'query_manifest_sha256':vis['query_manifest_sha256'],
             'fusion_weights':WEIGHTS,'fusion_method':'weighted RRF60 over branch top-20; renormalize available branches'}
        output.append(row)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output))
    print(json.dumps({'cases':len(output),'ocr_present':len(ocr),
                      'diagnostic_batch_over_10s':sum(x['diagnostic_batch_over_10s'] for x in output)}))
if __name__=='__main__':main()
