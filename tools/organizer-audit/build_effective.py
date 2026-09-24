"""Prefer frozen v1 outputs for exact-byte repeated organizer images.

No labels or gold are read. The three eval aliases reuse the corresponding
100-photo record by SHA. Fresh outputs remain archived for replicate analysis.
"""
import json
from pathlib import Path

ROOT=Path('/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit')
V1=Path('/Users/skif/ml-data/brutforce/eval-v1')
OLD=Path('/Users/skif/ml-data/brutforce/vision-baselines-20260924')
FILES={'deepseek':'deepseek-prompt-v1.jsonl','qwen':'qwen-prompt-v1.jsonl','paddle':'paddle.jsonl'}

def read(path):return [json.loads(s) for s in path.read_text().splitlines()]

def main():
    suite={x['image_sha256']:x['case_id'] for x in json.loads((V1/'baskets/v1.json').read_text())['cases']}
    queries=json.loads((ROOT/'queries-public.json').read_text())['cases']
    for model,filename in FILES.items():
        old={x['case_id']:x for x in read(OLD/filename)}
        fresh={x['case_id']:x for x in read(ROOT/f'{model}-standalone.jsonl')}
        bysha={};rows=[]
        for q in queries:
            sha=q['sha256'];cid=q['case_id']
            if sha in bysha:
                row=dict(bysha[sha]);row['case_id']=cid;row['source_set']=q['source_set'];row['reuse']='duplicate_image_same_sha';row['reuse_source_case_id']=bysha[sha]['case_id']
            elif sha in suite and suite[sha] in old:
                row=dict(old[suite[sha]]);row['case_id']=cid;row['image_sha256']=sha;row['source_set']=q['source_set'];row['reuse']='frozen_v1_exact_sha_same_prompt_matcher';row['reuse_source_case_id']=suite[sha]
            else:
                row=dict(fresh[cid]);row['reuse']='fresh_original_image';row['reuse_source_case_id']=None
            row['matcher_version']='vision-baselines-v1'
            rows.append(row)
            bysha.setdefault(sha,row)
        path=ROOT/f'{model}-organizer-effective.jsonl'
        path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
        print(model,len(rows),{k:sum(x['reuse']==k for x in rows) for k in ('frozen_v1_exact_sha_same_prompt_matcher','fresh_original_image','duplicate_image_same_sha')})

if __name__=='__main__':main()
