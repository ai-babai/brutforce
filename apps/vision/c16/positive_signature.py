"""Bounded positive product+colour scoring. Unknown catalogue values stay ranked."""
import hashlib,json,math
from candidate_policy import canonical_norm,contradicted,TITLE_STOP
from field_contract import core_token,COMMON_COUNTRY_CONTEXTS
VERSION='resource_abort_positive_known_product_color_signature-v1'
STRONG=('semantic_expansion_override','title_override','coherent_support_override','local_grape_override','resource_semantic_override')

def actual_word90(field_result,key,value):
 proofs=[]
 for e in field_result.get('evidence',[]):
  if e.get('accepted') is not True or e.get('key')!=key or e.get('value')!=value:continue
  proof=e.get('actual_word90_proof',{});word=proof.get('raw_TSV_binding',{});call=e.get('call');calls=field_result.get('calls',[])
  if proof.get('accepted') is not True or not isinstance(call,int) or not 0<=call<len(calls):continue
  if not math.isfinite(word.get('confidence',float('nan'))) or word['confidence']<90 or core_token(e.get('literal','')) is None:continue
  actual=calls[call]
  if actual.get('errors') or not actual.get('raw_TSV') or not actual.get('raw_hOCR') or sum(w==word for w in actual.get('TSV_words',[]))!=1:continue
  if word.get('text')!=e['literal'] or not e.get('source_box') or not e.get('source_transform'):continue
  proofs.append({'literal':e['literal'],'actual_TSV_float_confidence':word['confidence'],'actual_word_box':word['box'],'source_box':e['source_box'],'source_transform':e['source_transform'],'call':call,'actual_same_process_outputs_sha256':hashlib.sha256((actual['raw_TSV']+'\n'+actual['raw_hOCR']).encode()).hexdigest(),'character_geometry_result_retained':e.get('character90_geometry_proof'),'correlation_group':e.get('physical_source_group')})
 return proofs

def decide(base_order,current_order,field_result,reliable_query,raw_query,families,contexts,precall_abort,prior_overrides):
 base=[int(i) for i in base_order[:20]];current=[int(i) for i in current_order];flags={'version':VERSION,'override':False,'scope':'originalTop20_positive_known_signature_with_originalTop5_visual_support','unknown_is_not_contradiction':True,'globally_unique_compatible_identity_claimed':False}
 def stop(reason):return current,dict(flags,reason=reason)
 if any(prior_overrides.get(k) for k in STRONG):return stop('prior_independent_override_preserved')
 if precall_abort.get('reason') not in ('component_limit','foreground_limit','merge_pair_limit') or precall_abort.get('OCR_calls',0)!=0:return stop('measured_precall_resource_abort_required')
 if not base or len(set(base))!=len(base) or set(current[:20])!=set(base):return stop('invalid_original_scope')
 acquired=field_result.get('accepted_fields',{});p=acquired.get('product',[]);c=acquired.get('color',[])
 if len(p)!=1 or len(c)!=1:return stop('complete_product_and_color_required')
 product=canonical_norm(p[0]);color=c[0];grape_words=set(' '.join(families.attributes.vocab).split());producer_words=set(families.producer[base[0]].split())
 if len(product.split())!=1 or product in grape_words or product in TITLE_STOP or product in COMMON_COUNTRY_CONTEXTS or product in producer_words:return stop('product_is_variety_producer_or_standard_descriptor')
 if len(raw_query.get('grape',[]))>1:return stop('raw_blend_uncertainty_preserved')
 query={k:set(reliable_query.get(k,()))|set(acquired.get(k,())) for k in ('grape','color','sugar')}
 if any(len(v)>1 for v in query.values()):return stop('conflicting_reliable_fields')
 product_proof=actual_word90(field_result,'product',p[0]);color_proof=actual_word90(field_result,'color',color)
 if not product_proof or not color_proof:return stop('actual_complete_word90_channels_required')
 # Correction is supported by positive queryfields and an explicit KNOWN
 # original-head colour contradiction; unknown values never count as conflict.
 head=families.attributes.rows[base[0]]
 if not head['color'] or color in head['color']:return stop('original_head_known_color_contradiction_required')
 compatible=[];known=[];unknown=[];contradictions=[]
 for i in base:
  if families.producer[i]!=families.producer[base[0]]:continue
  row=families.attributes.rows[i]
  if contradicted(row,query):contradictions.append(i);continue
  compatible.append(i)
  full=contexts[i]
  # Complete positively matching source context only, not prefix/substring.
  if full==product and row['color']=={color} and not any(query[k] and not row[k] for k in ('grape','sugar')) and i in families.candidates(base[0],base):known.append(i)
  else:unknown.append(i)
 flags.update(known_positive_signatures=known,compatible_unknown_or_nonmatching=unknown,known_reliable_contradictions=contradictions,query={k:sorted(v) for k,v in query.items()},product=product,word90_proofs={'product':product_proof,'color':color_proof},unknown_membership_retained=True)
 if len(known)!=1 or known[0] not in base[:5]:return stop('no_unique_fully_observed_originalTop5_positive_signature')
 winner=known[0];selected=[winner]+[i for i in current if i!=winner]
 return selected,dict(flags,override=winner!=current[0],selected_index=winner,reason='positive_known_signature_outweighs_known_head_conflict_unknowns_still_ranked')
