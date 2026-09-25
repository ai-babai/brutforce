"""Prepare gold-blind fixed-B inputs; never load evaluation answers."""
import argparse,json,hashlib,shutil
from pathlib import Path
from PIL import Image,ImageOps

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cards',type=Path,required=True);a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=True);(a.out/'crops').mkdir(exist_ok=True)
 cards={r['slug']:{k:r.get(k) for k in ['slug','title','winery','category','region','grapes']} for r in map(json.loads,a.cards.read_text().splitlines())}
 (a.out/'cards.json').write_text(json.dumps(cards,ensure_ascii=False))
 rows=[]
 for dataset in ['eval','organizer']:
  public=json.loads((a.source/(dataset+'-public.json')).read_text());paths={r['case_id']:r for r in public['cases']}
  for row in map(json.loads,(a.source/('softgate-B-'+dataset+'.jsonl')).read_text().splitlines()):
   ident=row['case_id'];src=a.source/'input-stage'/paths[ident]['path'];assert sha(src)==row['query_sha256']
   res=row['result'];sel=res.get('selection') or {};box=sel.get('selected_box');rect=res.get('label_context_box')
   crop=None
   if box and res.get('ranked_slugs'):
    with Image.open(src) as raw:im=ImageOps.exif_transpose(raw).convert('RGB')
    im=im.crop(box)
    if rect:im=im.crop(rect)
    crop='crops/'+ident+'.png';im.save(a.out/crop)
   rows.append({'case_id':ident,'track':row['track'],'dataset':dataset,'query_sha256':row['query_sha256'],'query_path':paths[ident]['path'],'target_box':box,'label_box':rect,'crop':crop,'crop_sha256':sha(a.out/crop) if crop else None,'ocr_text':res.get('ocr_text',''),'candidates':res.get('ranked_slugs',[]),'baseline_row':row})
 (a.out/'inputs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
 (a.out/'prepare-receipt.json').write_text(json.dumps({'rows':len(rows),'cropped':sum(bool(r['crop']) for r in rows),'input_sha256':sha(a.out/'inputs.jsonl'),'catalog_cards':len(cards),'gold_loaded':False},indent=2))
 print((a.out/'prepare-receipt.json').read_text())
if __name__=='__main__':main()
