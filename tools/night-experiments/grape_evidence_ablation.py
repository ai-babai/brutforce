# -*- coding: utf-8 -*-
"""Fixed, gold-blind varietal contradictions on B Top20; not absence calibration."""
import argparse,copy,hashlib,json,re,time
from pathlib import Path

# Vocabulary is semantic and catalog-independent. No case IDs or target answers.
ALIASES={
 'cabernet_sauvignon':['cabernet sauvignon','каберне совиньон','каберне совиньон'],
 'cabernet_franc':['cabernet franc','каберне фран'],
 'sauvignon_blanc':['sauvignon blanc','совиньон блан','совиньон белый'],
 'pinot_noir':['pinot noir','пино нуар'], 'pinot_gris':['pinot gris','pinot grigio','пино гри','пино гриджо'],
 'pinot_blanc':['pinot blanc','пино блан'], 'chardonnay':['chardonnay','шардоне'],
 'riesling':['riesling','рислинг'], 'merlot':['merlot','мерло'],
 'syrah':['syrah','shiraz','сира','шираз'], 'saperavi':['saperavi','саперави'],
 'malbec':['malbec','мальбек'], 'tempranillo':['tempranillo','темпранильо'],
 'sangiovese':['sangiovese','санджовезе'], 'viognier':['viognier','вионье'],
 'gewurztraminer':['gewurztraminer','gewürztraminer','гевюрцтраминер'],
 'aligote':['aligote','aligoté','алиготе'], 'rkatsiteli':['rkatsiteli','ркацители'],
 'krasnostop':['красностоп золотовский','красностоп','krasnostop'],
 'tsimlyansky':['цимлянский черный','цимлянский чёрный'],
 'muscat':['muscat','moscato','мускат','мускат белый','мускат розовый'],
}
def normalize(text):
 return re.sub(r'\s+',' ',text.lower().replace('ё','е').replace('-',' ')).strip()
def observed(text):
 text=normalize(text)
 return {k for k,variants in ALIASES.items() if any(re.search(r'(?<!\w)'+re.escape(normalize(v))+r'(?!\w)',text) for v in variants)}
def catalog_grapes(card):
 chunks=re.split('[,;/]',card.get('grapes',''))
 result=set()
 for chunk in chunks:
  chunk=normalize(chunk)
  if not chunk:return set()
  matched={k for k,vs in ALIASES.items() if chunk in {normalize(v) for v in vs}}
  if len(matched)!=1:return set() # incomplete/ambiguous metadata is unknown
  result.update(matched)
 return result

def main():
 p=argparse.ArgumentParser()
 for x in ('source','cards','suite','out'):p.add_argument('--'+x,type=Path,required=True)
 a=p.parse_args();cards=json.loads(a.cards.read_text());suite=json.loads(a.suite.read_text());a.out.mkdir(parents=True,exist_ok=True)
 assert observed('CABERNET SAUVIGNON MERLOT')=={'cabernet_sauvignon','merlot'}
 assert observed('semi-rieslingish')==set()
 assert catalog_grapes({'grapes':'Мерло, неизвестный'})==set()
 cat={k:catalog_grapes(v) for k,v in cards.items()};summary={};by_id={}
 for ds,expected in [('eval',213),('organizer',103)]:
  rows=[json.loads(l) for l in (a.source/f'softgate-B-{ds}.jsonl').read_text().splitlines()];assert len(rows)==expected
  output=[];n_changed=n_applied=0
  for source in rows:
   row=copy.deepcopy(source);res=row['result'];rank=res.get('ranked_slugs',[]);t=time.perf_counter();seen=observed(res.get('ocr_text',''))
   conflict=[]
   if len(seen)==1:
    conflict=[s for s in rank if cat.get(s) and not(seen&cat[s])]
   # Stable partition: unknown/compatible keep B order; contradictions move down.
   new=[s for s in rank if s not in conflict]+conflict
   assert len(new)==len(rank) and set(new)==set(rank)
   n_applied+=bool(conflict);n_changed+=new!=rank
   if new:res.update(slug=new[0],ranked_slugs=new)
   res['grape_evidence']={'observed':sorted(seen),'demoted':conflict,'policy':'single explicit grape; fully parsed catalog grape metadata; no confidence claim'}
   row['elapsed_ms']=(time.perf_counter()-t)*1000;row['timing_scope']='cached_B_evidence_rule_only';output.append(row)
   if ds=='eval':by_id[row['case_id']]=row
  (a.out/f'{ds}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output));summary[ds]={'rows':len(rows),'applied':n_applied,'rank_changed':n_changed}
 for track in ['service','retrieval']:
  results=[]
  for case in suite['cases']:
   if case['tracks']!=[track]:continue
   row=by_id[case['case_id']];assert row['query_sha256']==case['image_sha256'];res=row['result'];rank=res.get('ranked_slugs',[])
   pred=({'slug':rank[0]} if rank else {'action':res.get('action','insufficient_information')}) if track=='service' else {'ranked_slugs':rank}
   results.append({'case_id':case['case_id'],'status':'ok' if row['http_status']==200 else 'error','prediction':pred,'latency_ms':round(row['elapsed_ms'])})
  sub={'submission_id':f'night-grape-evidence-{track}','suite_version':suite['version'],'suite_hash':suite['suite_hash'],'track':track,'basket_ids':[b['basket_id'] for b in suite['baskets'] if b['track']==track],'solution':{'name':'B + explicit grape contradiction (cached rule timing only)','version':'night-grape-v1','config_hash':hashlib.sha256(Path(__file__).read_bytes()+a.cards.read_bytes()).hexdigest(),'weights_version':'fixed B','catalog_version':'organizer-catalog-20260919'},'submitted_by':'night-coordinator','results':results}
  (a.out/f'{track}.json').write_text(json.dumps(sub,ensure_ascii=False,indent=2)+'\n')
 (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
