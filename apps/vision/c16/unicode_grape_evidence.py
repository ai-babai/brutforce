"""Additive exact whole Unicode grape channel; reuses frozen physical guards.
Only declarations in the global catalog vocabulary; no product-title shortcuts.
"""
from candidate_policy import canonical_norm
from character_acquisition import grape_alias_lexicon
from title_evidence import verify_word
VERSION='whole-unicode-grape-existing-geometry-v1'

def verify(word,pixels,catalog_vocab,word_confidence=None):
    class Vocabulary:vocab=set(catalog_vocab)
    # Alias normalization stays global, retains exact phrase boundaries and
    # ambiguous canonical rows; no single token from a multiword alias accepted.
    lexicon={}
    for alias,values in grape_alias_lexicon(Vocabulary()).items():
        token=canonical_norm(alias)
        if len(token.split())==1:lexicon.setdefault(token,set()).update(values)
    item=verify_word(word,pixels,set(lexicon),word_confidence=word_confidence)
    result=dict(item,evidence_version=VERSION,accepted_grapes=[],confidence_type='hocr_word90' if word_confidence is not None else 'hocr_character90',raw_word_confidence=word_confidence)
    if not item['accepted']:return result
    values=lexicon.get(item['value'],set())
    if len(values)!=1:return dict(result,accepted=False,reason='ambiguous_exact_global_grape_alias')
    return dict(result,key='grape',value=next(iter(values)),accepted_grapes=sorted(values),reason='exact_complete_global_grape_existing_physical_geometry_verified')
