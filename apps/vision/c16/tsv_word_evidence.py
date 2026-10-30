"""Existing one-word90 criterion with actual float TSV, never rounded hOCR."""
import csv,io,math,re,unicodedata
from candidate_policy import canonical_norm
VERSION='same-pass-actual-TSV-word90-v1'

def parse(raw):
    words=[]
    for row in csv.DictReader(io.StringIO(raw),delimiter='\t',quoting=csv.QUOTE_NONE):
        if row.get('level')!='5' or not row.get('text','').strip():continue
        x,y,w,h=[int(row[k]) for k in ('left','top','width','height')]
        words.append({'text':row['text'],'confidence':float(row['conf']),'box':[x,y,x+w,y+h]})
    return words

def verify(word,tsv_words,image_size,lexicon):
    literal=''.join(c.get('char','') for c in word.get('chars',[]))
    match=re.search(r'bbox (\d+) (\d+) (\d+) (\d+)',word.get('title',''))
    result={'version':VERSION,'accepted':False,'literal':literal,'confidence_type':'actual_TSV_float_word90','independent_character_proof':False}
    def no(reason):return dict(result,reason=reason)
    if not match:return no('missing_word_box')
    box=list(map(int,match.groups()));w,h=image_size
    if not (0<box[0]<box[2]<w and 0<box[1]<box[3]<h):return no('clipped_or_invalid_whole_word_box')
    same=[x for x in tsv_words if x['text']==literal and x['box']==box]
    if len(same)!=1:return no('missing_unique_same_pass_TSV_text_and_box')
    source=same[0];result.update(actual_TSV_word=source,box=box)
    confidence=source['confidence']
    if not math.isfinite(confidence) or confidence<90:return no('actual_float_word_below90')
    lo=0;hi=len(literal)
    while lo<hi and unicodedata.category(literal[lo]).startswith('P'):lo+=1
    while hi>lo and unicodedata.category(literal[hi-1]).startswith('P'):hi-=1
    core=literal[lo:hi];token=canonical_norm(core)
    if len(core)<5 or not core.isalpha() or token not in lexicon:return no('not_exact_complete_global_grape_token')
    values=lexicon[token]
    if len(values)!=1:return no('ambiguous_exact_global_grape_alias')
    return dict(result,accepted=True,accepted_grapes=sorted(values),alphabetic_core=core,boundary_positions=[lo,hi],reason='actual_same_pass_float_word90_exact_grape')
