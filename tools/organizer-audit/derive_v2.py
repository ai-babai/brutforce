"""Apply pre-existing generic cultivar rerank to cached organizer OCR."""
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vision-baselines'))
from matcher import Matcher
from offline_variants import v2_record

ROOT=Path('/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit')

def main():
    matcher=Matcher()
    for source_set in ('standalone','synthetic'):
        for model in ('deepseek','qwen'):
            inp=ROOT/f'{model}-{source_set}.jsonl'
            if not inp.exists():continue
            out=ROOT/f'{model}-{source_set}-matcher-v2.jsonl'
            source=[json.loads(s) for s in inp.read_text().splitlines()]
            with out.open('w') as f:
                for row in source:
                    rec=v2_record(row,matcher)
                    rec['matcher_version']='vision-baselines-v2-cached'
                    rec['reuse']='cached_ocr_same_original_image'
                    f.write(json.dumps(rec,ensure_ascii=False)+'\n')
            print(out.name,len(source))

if __name__=='__main__':main()
