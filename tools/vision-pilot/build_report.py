#!/usr/bin/env python3
"""Build aggregate report data from completed, local experimental artifacts."""
import argparse,json,statistics
from pathlib import Path
from generate import rows
from qa import ledger_accounting

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--baselines',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 summary=json.loads((a.root/'summary.json').read_text());manifest=rows(a.root/'manifest.jsonl');out=[r for r in manifest if r['role']=='output']
 aliases={'qwen/qwen-image-3':'Qwen Image 3','google/gemini-3.1-flash-image':'Nano Banana / Gemini 3.1 Flash Image','black-forest-labs/flux.2-pro':'FLUX.2 Pro'}
 gen=[]
 for model,stats in summary['by_model'].items():
  phase1=[r for r in out if r['model']==model and int(r['image_id'].split('-')[1])<=20];qc=stats['stage1']['qc'];accepted=qc.get('accepted',0)
  gen.append({'name':aliases[model],'outputs':stats['outputs'],'unit_cost':stats['cost_usd']/stats['outputs'],'accepted':accepted,'pending':qc.get('pending',0),'rejected':qc.get('rejected',0),'cost_per_accepted':sum(r['cost_usd'] for r in phase1)/accepted if accepted else None})
 specs=[('ds-v1-full','DeepSeek OCR + matcher v1',True,'2.55 / 2.82 s'),('qwen-v1-full','Qwen OCR + matcher v1',True,'2.47 / 2.82 s'),('paddle-v1-full','PaddleOCR CPU + matcher v1',True,'1.65 / 2.00 s'),('ds-matcher-v2','DeepSeek + matcher v2 (cached)',False,'reuses OCR'),('qwen-matcher-v2','Qwen + matcher v2 (cached)',False,'reuses OCR'),('rrf60-cached','DeepSeek + Qwen RRF60 (cached v1)',False,'modeled, not measured')]
 recognition=[]
 for prefix,name,base,latency in specs:
  service=json.loads((a.baselines/(prefix+'-service.report.json')).read_text())['overall']
  rp=a.baselines/(prefix+'-retrieval.report.json')
  if not rp.exists():rp=a.baselines/(prefix+'-retrieval-r1.report.json')
  retrieval=json.loads(rp.read_text())['overall']
  recognition.append({'name':name,'base':base,'service':service['correct_top1'],'top1':retrieval['correct_top1'],'top5':retrieval['correct_top5'],'top20':retrieval['correct_top20'],'latency':latency,'mrr':retrieval['mrr']})
 qa=sum(r.get('cost_usd',0) for r in rows(a.root/'qc-deepseek.jsonl') if r.get('status')=='completed')
 baseline_ledger=rows(a.baselines/'api-ledger.jsonl')
 baseline_cost=sum((r.get('usage') or {}).get('cost',0) for r in baseline_ledger)
 states={r['attempt_id']:r for r in rows(a.root/'runs/generation-ledger.jsonl')}
 uncertain=sum(r.get('cost_usd',r.get('reserve_usd',0)) for r in states.values() if r.get('status')!='complete')
 uncertain+=sum(r.get('reserved_usd') or 0 for r in baseline_ledger if not r.get('usage'))
 qa_conservative,qa_outcomes=ledger_accounting(a.root/'qa-ledger.jsonl')
 uncertain+=max(0,qa_conservative-qa)
 total=summary['generation_cost_usd']+qa+baseline_cost
 before=json.loads((a.root/'runs/budget.json').read_text())['openrouter_key_usage_before']
 after=json.loads((a.root/'runs/openrouter-final-usage.json').read_text())['usage']
 result={'outputs':summary['outputs'],'augmentations':summary['augmentations'],'wines':len({r['slug'] for r in out}),'generation':gen,'recognition':recognition,'generation_cost_usd':summary['generation_cost_usd'],'qa_cost_usd':qa,'recognition_cost_usd':baseline_cost,'confirmed_total_usd':total,'uncertain_reserve_usd':uncertain,'observed_key_usage_delta_usd':after-before,'unattributed_delta_usd':after-before-total,'qc_totals':{s:sum(r['qc']['status']==s for r in out) for s in ('accepted','pending','rejected')},'notes':['No RunPod created; final inventory zero.','QA calls include superseded v1 smoke.','Confirmed costs are response usage.cost, unknown failures retain conservative reserves.','Key-wide usage delta is a window observation, not per-call attribution.','100 outputs include 60 paired comparisons and 36 Qwen + 4 Banana fallback extension.']}
 a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(a.root/'report-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'confirmed_total_usd':total,'key_delta':after-before,'unattributed':after-before-total,'reserve':uncertain}))
if __name__=='__main__':main()
