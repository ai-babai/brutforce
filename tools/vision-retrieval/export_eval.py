"""Export cached branch-quality ablations to frozen public eval contract.

No gold is read. Latency is labelled cached stage sum, not a live HTTP claim.
"""
import argparse,hashlib,json
from pathlib import Path
from fuse import VARIANTS

def read_rows(path):return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--suite',type=Path,required=True);p.add_argument('--fused',type=Path,required=True)
 p.add_argument('--variant',choices=VARIANTS,required=True)
 p.add_argument('--track',choices=('service','retrieval'),required=True)
 p.add_argument('--submission-id',required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--label-context-v2',action='store_true')
 p.add_argument('--index-dir',type=Path,help='required for v2 index provenance')
 a=p.parse_args()
 if a.label_context_v2 and not a.index_dir:p.error('--label-context-v2 requires --index-dir')
 suite=json.loads(a.suite.read_text());by_id={x['case_id']:x for x in read_rows(a.fused)}
 cases=[x for x in suite['cases'] if x['tracks']==[a.track]]
 results=[]
 for c in cases:
  x=by_id.get(c['case_id'])
  if x is None:raise ValueError('missing case '+c['case_id'])
  if x['query_sha256']!=c['image_sha256']:raise ValueError('query hash mismatch '+c['case_id'])
  rank=x['variants_top20'][a.variant]
  if a.track=='service':pred=x['predictions'][a.variant]
  else:pred={'ranked_slugs':[r['slug'] for r in rank]}
  status='ok' if a.track=='service' or pred['ranked_slugs'] else 'error'
  result={'case_id':c['case_id'],'status':status,
          'latency_ms':int(x['variant_cached_stage_sum_ms'][a.variant])}
  if status=='ok':result['prediction']=pred
  results.append(result)
 baskets=sorted({b for c in cases for b in c['basket_ids'] if b.startswith('IMG-')==(a.track=='service')})
 sources=['model.py','index.py','vision_queries.py','ranking.py','fuse.py']
 if a.label_context_v2:sources.append('label_context_v2.py')
 config=hashlib.sha256(b''.join((Path(__file__).parent/name).read_bytes() for name in sources))
 index_hash=hashlib.sha256((a.index_dir/'index.npz').read_bytes()).hexdigest() if a.index_dir else None
 if index_hash:config.update(index_hash.encode())
 code=config.hexdigest()[:16]
 version='v2-label-context-offline' if a.label_context_v2 else 'v1-offline'
 name=('cached-label-context-v2-'+a.variant if a.label_context_v2
       else 'cached-quality-ablations-'+a.variant)
 submission={'submission_id':a.submission_id,'suite_version':suite['version'],'suite_hash':suite['suite_hash'],
             'track':a.track,'basket_ids':baskets,
             'solution':{'name':name,'version':version,
                         'commit':None,'config_hash':code,
                         'weights_version':'OWLv2 pinned + SigLIP2 pinned + PP-OCRv5 mobile',
                         'catalog_version':suite['catalog_sha256'][:16]},
             'submitted_by':'vision-retrieval','results':results}
 a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(json.dumps(submission,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'file':str(a.out),'results':len(results),'status_error':sum(r['status']=='error' for r in results),
                   'latency_kind':'offline_cached_stage_sum_not_live_http'}))
if __name__=='__main__':main()
