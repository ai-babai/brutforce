"""Add original catalog reference filename to every card, with CSV provenance.

No query annotations, inferred sweetness, or case-specific exceptions.
"""
import argparse,csv,hashlib,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--cards',type=Path,required=True);p.add_argument('--csv',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    cards=json.loads(a.cards.read_text());names={}
    with a.csv.open() as f:
        for row in csv.DictReader(f):
            slug=row['Slug'].strip();name=row['Название фото'].strip()
            if name:names.setdefault(slug,set()).add(name)
    conflicts=[];mapped=0
    for slug,c in cards.items():
        options=names.get(slug,set())
        if len(options)==1:c['reference_filename']=next(iter(options));mapped+=1
        elif len(options)>1:conflicts.append(slug)
    a.out.write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n')
    receipt={'cards':len(cards),'mapped':mapped,'conflicting_filenames':conflicts,'missing':len(cards)-mapped-len(conflicts),'input_cards_sha256':hashlib.sha256(a.cards.read_bytes()).hexdigest(),'source_csv_sha256':hashlib.sha256(a.csv.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(a.out.read_bytes()).hexdigest(),'rule':'Add unmodified original reference filename only when all CSV rows agree for a slug. No inferred fields; no test labels.'}
    a.out.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))

if __name__=='__main__':main()
