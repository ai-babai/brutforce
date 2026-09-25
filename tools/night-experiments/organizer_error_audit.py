# -*- coding: utf-8 -*-
"""Trusted diagnostic only; never pass this artifact to inference or the web root."""
import argparse,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);a=p.parse_args()
 labs=[json.loads(l) for l in a.labels.read_text().splitlines()];labs={r['sha256']:r for r in labs if r['status']=='exact'};assert len(labs)==54
 sources={'B':a.baseline,'Qwen20':a.root/'qwen/exported/top20-organizer.jsonl','Roman20':a.root/'roman/final/roman20-organizer.jsonl','grape_evidence':a.root/'grape-evidence/organizer.jsonl'}
 report={}
 for name,path in sources.items():
  rows={}
  for line in path.read_text().splitlines():
   row=json.loads(line);sha=row['query_sha256']
   if sha not in labs:continue
   result=row['result'];lab=labs[sha];rank=result.get('ranked_slugs',[]);review=lab.get('review',{})
   item={'case_id':row['case_id'],'sha256':sha,'expected_slug':lab['exact_slug'],'predicted_slug':result.get('slug'),'correct':row['http_status']==200 and result.get('slug')==lab['exact_slug'],'expected_rank':rank.index(lab['exact_slug'])+1 if lab['exact_slug'] in rank else None,'catalog_reference_conflict':bool(review.get('catalog_reference_conflict') or 'catalog_reference_conflict' in review.get('flags',[])),'scene_group':lab.get('scene_group'),'annotation_evidence':lab.get('evidence_text'),'selection':result.get('selection',{}),'ocr_text':result.get('ocr_text','')}
   if sha in rows:assert all(item[k]==rows[sha][k] for k in ['correct','expected_rank','predicted_slug'])
   else:rows[sha]=item
  vals=list(rows.values());assert len(vals)==54
  conflict=[v for v in vals if v['catalog_reference_conflict']];ordinary=[v for v in vals if not v['catalog_reference_conflict']]
  report[name]={'primary':{'correct':sum(v['correct'] for v in vals),'total':54},'known_reference_conflict_slice':{'correct':sum(v['correct'] for v in conflict),'total':len(conflict)},'without_known_reference_conflict_slice':{'correct':sum(v['correct'] for v in ordinary),'total':len(ordinary)},'errors':[v for v in vals if not v['correct']]}
 target=a.root/'common/error-audit-organizer.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');target.chmod(0o600)
 print(json.dumps({k:{key:v for key,v in value.items() if key!='errors'} for k,value in report.items()}))
if __name__=='__main__':main()
