"""Exploratory equal RRF of two complete, fixed-pool blind result sets.

Quality diagnostic only. Timer covers rank merging, not either neural model.
"""
import argparse,copy,json,time
from pathlib import Path

def read(path):return [json.loads(l) for l in path.read_text().splitlines()]
def main():
    p=argparse.ArgumentParser();p.add_argument('--qwen',type=Path,required=True);p.add_argument('--roman',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    roman=read(a.roman);assert len(roman)==316
    by={r['case_id']:r for r in roman};assert len(by)==316
    for ds in ['eval','organizer']:
        results=[]
        for row in read(a.qwen/('top20-'+ds+'.jsonl')):
            rr=by[row['case_id']];assert rr['query_sha256']==row['query_sha256']
            r=rr['roman20']['ranked_slugs'];q=row['result'].get('ranked_slugs',[])
            assert set(r)==set(q) and len(r)==len(q)
            start=time.perf_counter();weights={s:1/(61+i) for i,s in enumerate(r)}
            for i,s in enumerate(q):weights[s]+=1/(61+i)
            rank=sorted(r,key=lambda s:(-weights[s],r.index(s)))
            out=copy.deepcopy(row)
            if rank:out['result'].update(slug=rank[0],ranked_slugs=rank)
            out['elapsed_ms']=(time.perf_counter()-start)*1000
            out['timing_scope']='cached_rank_merging_only_not_either_model'
            out['result']['ensemble_trace']={'rrf_k':60,'weights':[1,1],'tie_break':'Roman20 rank','exploratory_same_suite':True}
            results.append(out)
        (a.out/(ds+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results))

if __name__=='__main__':main()
