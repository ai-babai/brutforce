"""Catalog-filename lexical ablation, optional script normalization, no gold."""
import argparse,copy,json,sys,time
from pathlib import Path
from homoglyph_ablation import normalize

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--cards',type=Path,required=True);p.add_argument('--code',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--normalize',action='store_true');a=p.parse_args()
    sys.path.insert(0,str(a.code));from ranking import Lexical;from fuse import ocr_top,rank_fuse
    refs=json.loads(a.catalog.read_text())['references'];cards=json.loads(a.cards.read_text());slugs=[r['slug'] for r in refs]
    assert set(cards)==set(slugs) and len(slugs)==2103
    lex=Lexical([{'slug':r['slug'],'title':r.get('title','')+' '+Path(cards[r['slug']]['reference_filename']).stem,'producer':r.get('winery','')} for r in refs]);a.out.mkdir(parents=True,exist_ok=True)
    for ds in ('eval','organizer'):
        rows=[json.loads(l) for l in (a.source/('softgate-B-'+ds+'.jsonl')).read_text().splitlines()];out=[]
        for r in rows:
            row=copy.deepcopy(r);res=row['result'];text=res.get('ocr_text','');start=time.perf_counter()
            if a.normalize:text=normalize(text)
            branches=copy.deepcopy(res['branches_top20']);branches['ocr']=ocr_top(lex,text,slugs);ranking=rank_fuse(branches)
            if res.get('ranked_slugs'):res.update(slug=ranking[0]['slug'],ranked_slugs=[x['slug'] for x in ranking])
            res['branches_top20']=branches;res['ocr_text']=text;res['catalog_ocr_trace']={'add_reference_filename':True,'normalize_mixed_script':a.normalize}
            row['elapsed_ms']=(time.perf_counter()-start)*1000;row['timing_scope']='lexical_search_and_rank_merge_only_cached_B';out.append(row)
        (a.out/(ds+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out))

if __name__=='__main__':main()
