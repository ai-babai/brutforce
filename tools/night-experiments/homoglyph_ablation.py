"""One catalog-wide OCR normalization ablation; no gold/case-specific rules."""
import argparse,copy,json,re,sys,time
from pathlib import Path

LOOKALIKE=str.maketrans({'A':'А','B':'В','C':'С','E':'Е','H':'Н','K':'К','M':'М','O':'О','P':'Р','T':'Т','X':'Х','Y':'У','a':'а','c':'с','e':'е','o':'о','p':'р','x':'х','y':'у'})
def normalize(text):
 def word(m):
  token=m.group()
  return token.translate(LOOKALIKE) if re.search('[А-Яа-яЁё]',token) and re.search('[A-Za-z]',token) else token
 return re.sub(r'[A-Za-zА-Яа-яЁё0-9]+',word,text)

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--code',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 sys.path.insert(0,str(a.code));from ranking import Lexical;from fuse import ocr_top,rank_fuse
 refs=json.loads(a.catalog.read_text())['references'];slugs=[r['slug'] for r in refs]
 lex=Lexical([{'slug':r['slug'],'title':r.get('title',''),'producer':r.get('winery','')} for r in refs])
 a.out.mkdir(parents=True,exist_ok=True);summary={}
 for dataset in ['eval','organizer']:
  rows=[json.loads(l) for l in (a.source/('softgate-B-'+dataset+'.jsonl')).read_text().splitlines()];changedtext=0;changedrank=0;out=[]
  for r in rows:
   row=copy.deepcopy(r);res=row['result'];before=res.get('ocr_text','');after=normalize(before);changedtext+=before!=after
   t=time.perf_counter();branches=copy.deepcopy(res['branches_top20']);branches['ocr']=ocr_top(lex,after,slugs);rank=rank_fuse(branches)
   old=res.get('ranked_slugs',[])
   new=[i['slug'] for i in rank] if old else []
   changedrank+=old!=new
   res['ocr_text']=after;res['branches_top20']=branches
   if new:res.update(slug=new[0],ranked_slugs=new)
   row['normalization_trace']={'before':before,'after':after,'extra_ms':(time.perf_counter()-t)*1000,'policy':'Latin lookalikes to Cyrillic only in mixed-script tokens; no digit substitution'}
   row['timing_scope']='cached_B_original_HTTP_timing_not_new_live_run'
   out.append(row)
  (a.out/(dataset+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out));summary[dataset]={'rows':len(rows),'changed_text':changedtext,'changed_rank':changedrank}
 (a.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()
