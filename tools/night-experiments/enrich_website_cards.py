# -*- coding: utf-8 -*-
"""Uniform supplementary website metadata; frozen IDs and images are unchanged."""
import argparse,hashlib,json,re
from collections import Counter
from pathlib import Path

def norm(s):return re.sub(r'\W','',s.lower())
def main():
 p=argparse.ArgumentParser()
 for k in ['cards','website','out']:p.add_argument('--'+k,type=Path,required=True)
 a=p.parse_args();cards=json.loads(a.cards.read_text());rows=[json.loads(l) for l in a.website.read_text().splitlines()];by={r['slug']:r for r in rows};assert len(rows)==len(by)
 counts=Counter();excluded=[];provenance={}
 for slug,card in cards.items():
  source=by.get(slug)
  if source is None:counts['no_direct_slug']+=1;excluded.append({'slug':slug,'reason':'no_direct_slug'});continue
  if norm(card.get('title',''))!=norm(source.get('title','')) or norm(card.get('winery',''))!=norm(source.get('producer','')):
   counts['identity_text_differs']+=1;excluded.append({'slug':slug,'reason':'identity_text_differs'});continue
  card['website_category_and_sweetness']=source.get('category_and_sweetness','')
  card['website_sweetness']=source.get('sweetness','')
  counts['supplemented']+=1
  provenance[slug]={'source_url':source.get('source_url'),'snapshot_date':source.get('source_snapshot_date'),'matching':'direct slug, normalized title and producer agreement'}
 assert len(cards)==2103
 a.out.write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n')
 receipt={'policy':'Supplement only category_and_sweetness/sweetness from the recorded public website catalog, with direct slug AND normalized title/producer agreement. Unknown/conflicting rows retain base fields. No alias inference, query annotation, rank, image, or gold change. This is an additional metadata input, not the original CSV-only baseline.','counts':dict(counts),'excluded':excluded,'provenance':provenance,'input_cards_sha256':hashlib.sha256(a.cards.read_bytes()).hexdigest(),'source_website_sha256':hashlib.sha256(a.website.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(a.out.read_bytes()).hexdigest()}
 a.out.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'counts':dict(counts),'output_sha256':receipt['output_sha256']}))
if __name__=='__main__':main()
