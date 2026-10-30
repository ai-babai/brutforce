"""Predicate-only review checks; no model, OCR, gold or held-out inputs."""
from types import SimpleNamespace
from PIL import Image,ImageDraw
import numpy as np
from title_evidence import verify_word
from title_verification import decide
from title_catalog import TitleCatalog
from title_geometry import non_title_row,language_plan

def run():
    checks=[]
    def check(name,value):
        assert value,name
        checks.append(name)
    def glyph_word(text='ШАРДОНЕ',conf=95):
        im=Image.new('L',(len(text)*14,25),255);d=ImageDraw.Draw(im);chars=[]
        for i,c in enumerate(text):
            d.rectangle((i*14+2,3,i*14+5,21),fill=0)
            chars.append({'char':c,'title':f'x_bboxes {i*14} 2 {i*14+10} 22; x_conf {conf}'})
        return {'title':f'bbox 0 0 {len(text)*14} 25; x_wconf 95','chars':chars},im
    w,im=glyph_word();check('exact_whole_high_character_token',verify_word(w,im,{'shardone'})['accepted'])
    w,im=glyph_word(conf=89);check('low_character_not_trusted',not verify_word(w,im,{'shardone'})['accepted'])
    w,im=glyph_word('ШАРДОН');check('truncated_grape_rejected',not verify_word(w,im,{'shardone'})['accepted'])
    w,im=glyph_word();w['chars'][1]['title']=w['chars'][0]['title'];check('word90_cannot_bypass_overlap',not verify_word(w,im,{'shardone'},word_confidence=95)['accepted'])
    w,im=glyph_word();check('word90_cannot_bypass_solid_ink',not verify_word(w,Image.new('L',im.size,0),{'shardone'},word_confidence=95)['accepted'])
    attrs=SimpleNamespace(rows=[dict(grape={'shardone'},color={'white'},sugar={'dry'}),dict(grape={'shardone'},color={'white'},sugar={'dry'}),dict(grape={'shardone'},color={'white'},sugar={'dry'})],vocab={'shardone','rkatsiteli'})
    families=SimpleNamespace(attributes=attrs,producer=['p']*3)
    catalog=TitleCatalog([{'title':'Шардоне regular'},{'title':'Шардоне reserve'},{'title':'Шардоне - Ркацители'}],families)
    check('raw_catalog_blend_is_unknown_title',catalog.context[2]=='')
    catalog=TitleCatalog([{'title':'Шардоне regular','slug':'regular','sha256':'0'},{'title':'Шардоне reserve','slug':'reserve','sha256':'1'}],SimpleNamespace(attributes=SimpleNamespace(rows=attrs.rows[:2],vocab=attrs.vocab),producer=['p','p']))
    acq={'accepted':True,'role':'following_product_title_row','trusted_grapes':['shardone'],'proof_contract':'query_reliable_whole_grape'}
    refs={i:{'accepted':True,'role':'following_product_title_row','catalog_grapes':['shardone'],'proof_contract':'reference_catalog_identity_raw_OCR_location','source_sha256':str(i),'catalog_index':i,'catalog_slug':['regular','reserve'][i],'catalog_sha256':'catalog','box':[0,0,100,100]} for i in [0,1]}
    out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs);check('positive_independent_title_comparison',f['title_override'] and list(out)==[1,0])
    out,f=decide([0,1],[0,1],{},catalog,acq,{0:.76,1:.80},refs);check('small_margin_abstains',not f['title_override'])
    out,f=decide([0,1],[0,1],{},catalog,acq,{0:.60,1:.69},refs);check('low_similarity_abstains',not f['title_override'])
    out,f=decide([0,1],[0,1],{'color':{'red'}},catalog,acq,{0:.71,1:.80},refs);check('known_semantic_conflict_abstains',not f['title_override'])
    out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs,raw_multi_grape=True);check('raw_blend_abstains',not f['title_override'])
    refs[1]['source_sha256']='0';out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs);check('same_physical_reference_not_independent',not f['title_override'])
    refs[1]['source_sha256']='1';acq['role']='upper_logo';out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs);check('upper_logo_not_product_title',not f['title_override'])
    acq['role']='following_product_title_row';catalog.context[1]='';out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs);check('unknown_compatible_contender_abstains',not f['title_override'])
    acq['proof_contract']='reference_catalog_identity_raw_OCR_location';out,f=decide([0,1],[0,1],{},catalog,acq,{0:.71,1:.80},refs);check('query_cannot_borrow_reference_contract',not f['title_override'])
    check('numeric_vintage_not_title',non_title_row('2023',{'shardone'}) is not None)
    check('date_not_title',non_title_row('05.10.2026',{'shardone'}) is not None)
    check('common_attribute_not_title',non_title_row('Белое сухое',{'shardone'}) is not None)
    check('unknown_cursive_not_rejected_by_absence',non_title_row('Cukopy',{'shardone'}) is None)
    catalog.context[1]='reserve';catalog.rows[1]['grape']={'shardone','rkatsiteli'};check('compatible_complete_blend_unknown_not_rejected',1 in catalog.contenders(0,[0,1])['unknown'])
    catalog.rows[1]['grape']={'shardone'};catalog.rows[1]['color']=set();check('trusted_query_unknown_field_blocks',1 in catalog.contenders(0,[0,1],{'color':{'white'}})['unknown'])
    check('Latin_logo_cannot_exclude_query_Cyrillic',language_plan('SIKORY')['language']=='rus+eng')
    check('empty_prior_covers_both_query_languages',language_plan('')['language']=='rus+eng')
    check('reference_cache_identity_contract_kept',language_plan('Шардоне',{'shardone'})['language']=='rus')
    return {'pass':True,'checks':checks,'count':len(checks),'no_model_no_ocr':True}
if __name__=='__main__':
    import json
    print(json.dumps(run(),indent=2))
