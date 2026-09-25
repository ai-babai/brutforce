"""Export complete fixed-pool rerank ablations. No gold is read."""
import argparse,copy,hashlib,json
from pathlib import Path


def reorder(original,scores,mode):
    if not scores:return original
    assert len(original)==len(scores)
    q=sorted(range(len(original)),key=lambda i:(-scores[i],i))
    if mode=='top5':
        q5=sorted(range(min(5,len(original))),key=lambda i:(-scores[i],i))
        return [original[i] for i in q5]+original[5:]
    if mode=='fusion':
        ranks={idx:rank+1 for rank,idx in enumerate(q)}
        q=sorted(range(len(original)),key=lambda i:(-(1/(60+i+1)+1/(60+ranks[i])),i))
    if mode=='confident':
        # Engineering threshold, not calibrated probability or OOD detection.
        if scores[q[0]]<.8 or (len(q)>1 and scores[q[0]]-scores[q[1]]<.2):return original
    return [original[i] for i in q]


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--scores',type=Path,required=True);p.add_argument('--suite',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    inputs=[json.loads(l) for l in (a.stage/'inputs.jsonl').read_text().splitlines()]
    scores=[json.loads(l) for l in a.scores.read_text().splitlines()]
    by={r['case_id']:r for r in scores};assert len(by)==len(scores)==len(inputs)==316
    assert set(by)=={r['case_id'] for r in inputs}
    suite=json.loads(a.suite.read_text());assert suite['version']=='v2'
    config=hashlib.sha256(a.scores.with_name('config.json').read_bytes()+Path(__file__).read_bytes()).hexdigest()
    a.out.mkdir(parents=True,exist_ok=True)
    for mode in ['top20','top5','fusion','confident']:
        rows={key:[] for key in ['eval','organizer']}
        for source in inputs:
            s=by[source['case_id']];assert s['query_sha256']==source['query_sha256'] and s['candidates']==source['candidates']
            row=copy.deepcopy(source['baseline_row']);result=row['result'];old=result.get('ranked_slugs',[])
            if s['error']:
                # Explicit fail-open fallback. Failed computation remains in trace.
                new=old
            else:new=reorder(old,s['scores'],mode)
            if new:result.update(slug=new[0],ranked_slugs=new)
            result['rerank_trace']={'mode':mode,'error':s['error'],'fallback':bool(s['error']),'stage_ms':s['rerank_ms']}
            row['elapsed_ms']=s['rerank_ms'];row['timing_scope']='reranker_only_cached_B_inputs'
            rows[source['dataset']].append(row)
        for dataset,data in rows.items():
            (a.out/(mode+'-'+dataset+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data))
        byrow={r['case_id']:r for r in rows['eval']};assert set(byrow)=={c['case_id'] for c in suite['cases']}
        for track in ['service','retrieval']:
            results=[]
            for case in suite['cases']:
                if case['tracks']!=[track]:continue
                row=byrow[case['case_id']];res=row['result'];rank=res.get('ranked_slugs',[])
                assert row['query_sha256']==case['image_sha256']
                if row['http_status']==200:
                    if track=='service':pred={'slug':rank[0]} if rank else {'action':res.get('action','insufficient_information')}
                    else:pred={'ranked_slugs':rank[:20]}
                    status='ok'
                else:pred={};status='error'
                results.append({'case_id':case['case_id'],'status':status,'prediction':pred,'latency_ms':round(row['elapsed_ms'])})
            submission={'submission_id':'night-qwen-vl2b-'+mode+'-'+track,'suite_version':'v2','suite_hash':suite['suite_hash'],'track':track,'basket_ids':[b['basket_id'] for b in suite['baskets'] if b['track']==track],
              'solution':{'name':'Cached B → Qwen VL 2B '+mode+' (rerank timing only)','version':'night-20260925-'+mode,'config_hash':config,'weights_version':'Qwen3-VL-Reranker-2B@4bd860ac4f15','catalog_version':'organizer-catalog-20260919'},'submitted_by':'Sigma / nightly experiment','results':results}
            (a.out/(mode+'-'+track+'.json')).write_text(json.dumps(submission,ensure_ascii=False,indent=2)+'\n')
    print('Exported four exploratory variants; stage timing only; failures preserve B explicitly.')

if __name__=='__main__':main()
