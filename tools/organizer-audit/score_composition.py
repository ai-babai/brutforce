"""Reviewer-side aggregate only. Never ship labels to inference hosts."""
import argparse, hashlib, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--predictions',type=Path,required=True)
p.add_argument('--labels',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--ambiguous-case',action='append',default=[])
a=p.parse_args()
rows=[json.loads(x) for x in a.predictions.read_text().splitlines() if x.strip()]
by_id={x['case_id']:x for x in rows}
if len(by_id)!=len(rows):raise ValueError('duplicate case IDs')
labels=[x for x in json.loads(a.labels.read_text())['labels'] if x.get('expected_slug')]
if not labels:raise ValueError('no labeled cases')
variants=list(rows[0]['variants_top20'])
result={'scope':'development-only: local agent-reviewed labels, not organizer ground truth; all 10 labeled cases already in frozen v1',
        'prediction_sha256':hashlib.sha256(a.predictions.read_bytes()).hexdigest(),
        'labels_sha256':hashlib.sha256(a.labels.read_bytes()).hexdigest(),
        'query_rows':len(rows),'unique_images':len({x['query_sha256'] for x in rows}),
        'methods':{}}
for variant in variants:
 stats={}
 for name,subset in [('strict',labels),('excluding_ambiguous_balaklava',[x for x in labels if x['case_id'] not in a.ambiguous_case])]:
  ranks=[]
  for label in subset:
   row=by_id[label['case_id']]
   ranking=[x['slug'] for x in row['variants_top20'][variant]]
   if len(set(ranking))!=len(ranking):raise ValueError('duplicate ranked slug')
   ranks.append(ranking.index(label['expected_slug'])+1 if label['expected_slug'] in ranking else None)
  stats[name]={'count':len(subset),**{f'top{k}':sum(rank is not None and rank<=k for rank in ranks) for k in [1,5,20]},
               'mrr20':sum(1/rank if rank else 0 for rank in ranks)/len(subset) if subset else None}
 result['methods'][variant]=stats
a.out.parent.mkdir(parents=True,exist_ok=True)
a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
