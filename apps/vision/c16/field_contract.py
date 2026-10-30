"""Complete lexical field identities; products are not grape aliases."""
import math,re,unicodedata
from candidate_policy import canonical_norm,contradicted
from semantic_evidence import FORMS
from local_grape_acquisition import alias_map
KEYS=('grape','color','sugar','product')
COMMON_COUNTRY_CONTEXTS={canonical_norm(x) for x in ('Россия','России','Российское','France','Франция','Франции','Italy','Италия','Италии','Spain','Испания','Germany','Германия','Portugal','Португалия','Argentina','Аргентина','Chile','Чили','Georgia','Грузия','Armenia','Армения','Australia','Австралия','New Zealand','Новая Зеландия','South Africa','ЮАР','Turkey','Турция','Romania','Румыния','Moldova','Молдова','Azerbaijan','Азербайджан')}

def product_context(reference,producer):
    tokens=canonical_norm(reference.get('title','')).split();remove=set(producer.split())|{'vino','wine'}
    remove.update(x for values in FORMS.values() for aliases in values.values() for x in aliases)
    context=' '.join(x for x in tokens if x not in remove and not x.isdigit())
    return '' if context in COMMON_COUNTRY_CONTEXTS else context

def registry(vocab,references,families):
    result={};contexts=[product_context(r,families.producer[i]) for i,r in enumerate(references)]
    for token,values in alias_map(vocab).items():
        for value in values:result.setdefault(token,set()).add(('grape',value))
    for key,values in FORMS.items():
        if key!='color':continue
        for value,aliases in values.items():
            for alias in aliases:result.setdefault(alias,set()).add((key,value))
    # Metadata retains full multiword contexts. Acquisition conservatively
    # supports exact complete one-word contexts; no arbitrary phrase suffix.
    for context in contexts:
        if len(context.split())==1 and len(context)>=5 and context not in result:result.setdefault(context,set()).add(('product',context))
    return result,contexts

def core_token(text):
    a=0;b=len(text)
    while a<b and unicodedata.category(text[a]).startswith('P'):a+=1
    while b>a and unicodedata.category(text[b-1]).startswith('P'):b-=1
    core=text[a:b]
    return canonical_norm(core) if len(core)>=5 and core.isalpha() else None

def word90(word,tsv_words,size,lexicon):
    literal=''.join(x.get('char','') for x in word.get('chars',[]));match=re.search(r'bbox (\d+) (\d+) (\d+) (\d+)',word.get('title',''));item={'accepted':False,'literal':literal,'confidence_type':'actual_same_process_TSV_word90','raw_TSV_binding':None}
    if not match:return dict(item,reason='missing_word_box')
    box=list(map(int,match.groups()));w,h=size
    if not (0<box[0]<box[2]<w and 0<box[1]<box[3]<h):return dict(item,reason='clipped_word')
    same=[x for x in tsv_words if x['text']==literal and x['box']==box]
    if len(same)!=1:return dict(item,reason='not_one_same_process_literal_and_box')
    item['raw_TSV_binding']=same[0];confidence=same[0]['confidence']
    if not math.isfinite(confidence) or confidence<90:return dict(item,reason='actual_float_word_below90')
    token=core_token(literal);matches=lexicon.get(token,set())
    if len(matches)!=1:return dict(item,reason='not_one_complete_global_field_identity')
    key,value=next(iter(matches));return dict(item,accepted=True,key=key,value=value,reason='actual_float_word90_complete_field_identity')

def verify_selection(base_order,current_order,query,families,contexts):
    base=[int(i) for i in base_order[:20]];current=[int(i) for i in current_order];query={k:set(query.get(k,())) for k in KEYS};flags={'override':False,'original_top20':base,'query':{k:sorted(v) for k,v in query.items()}}
    if any(len(v)>1 for v in query.values()):return current,dict(flags,reason='conflicting_fields')
    if not query['grape'] and not (query['color'] and query['product']):return current,dict(flags,reason='no_complete_distinguishing_identity')
    if not base or not current or set(current[:20])!=set(base) or len(set(base))!=len(base):return current,dict(flags,reason='invalid_original_scope')
    candidates=families.candidates(base[0],base);known=[];unknown=[];rejected=[]
    if current[0] not in candidates:return current,dict(flags,reason='current_head_outside_original_semantic_group')
    if hasattr(families,'line'):
        unknown.extend(i for i in base if i not in candidates and families.producer[i]==families.producer[base[0]] and (not families.line[i] or not families.line[base[0]]) and not contradicted(families.attributes.rows[i],{k:v for k,v in query.items() if k!='product'}))
    for i in candidates:
        row=families.attributes.rows[i]
        if contradicted(row,{k:v for k,v in query.items() if k!='product'}):rejected.append(i);continue
        product=contexts[i];q=next(iter(query['product'])) if query['product'] else None
        if q and product and set(q.split()).isdisjoint(product.split()):rejected.append(i);continue
        if any(query[k] and not row[k] for k in ('grape','color','sugar')) or (q and (not product or product!=q)):unknown.append(i)
        else:known.append(i)
    flags.update(compatible_known=known,unknown=unknown,rejected=rejected)
    if unknown or len(known)!=1 or known[0] not in current:return current,dict(flags,reason='uncertain_or_nonunique_original_scope')
    winner=known[0];return [winner]+[i for i in current if i!=winner],dict(flags,override=winner!=current[0],selected=winner,reason='complete_positive_fields_unique_originalTop20')
