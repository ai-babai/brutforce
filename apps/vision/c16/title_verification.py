"""Independent title-region image verification hypothesis; no model invocation."""
import math
import numpy as np
from candidate_policy import KEYS,contradicted
MIN_SIMILARITY=.70
MIN_MARGIN=.05
VERSION='title-region-verification-v1-untuned-070-005'
def decide(base_order,current_order,query,catalog,acquisition,scores,reference_proofs,raw_multi_grape=False):
    result=np.asarray(current_order).copy();query={k:set(query.get(k,())) for k in KEYS}
    flags={'title_override':False,'version':VERSION,'minimum_similarity':MIN_SIMILARITY,'minimum_margin':MIN_MARGIN,'query':{k:sorted(v) for k,v in query.items()},'source':'independent_catalog_title_region_image_comparison','not_word_confidence':True}
    def no(reason):return result,dict(flags,reason=reason)
    if not len(base_order) or not len(result):return no('empty_rankings')
    if raw_multi_grape or any(len(v)>1 for v in query.values()):return no('trusted_conflict_or_raw_blend_uncertainty')
    if not acquisition.get('accepted') or acquisition.get('role')!='following_product_title_row' or acquisition.get('proof_contract')!='query_reliable_whole_grape':return no('no_complete_role_verified_query_row')
    grape=set(acquisition.get('trusted_grapes',[]))
    if len(grape)!=1 or (query['grape'] and query['grape']!=grape):return no('missing_or_conflicting_whole_grape_anchor')
    query['grape']|=grape;head=int(result[0]);c=catalog.contenders(int(base_order[0]),base_order,query);flags.update(contenders=c)
    if c['unknown']:return no('compatible_unknown_catalog_competitor')
    candidates=c['known']
    if head not in candidates or len({catalog.context[i] for i in candidates})<2:return no('no_distinct_known_line_ambiguity')
    if any(i not in reference_proofs or not reference_proofs[i].get('accepted') or reference_proofs[i].get('role')!='following_product_title_row' or set(reference_proofs[i].get('catalog_grapes',[]))!=grape or reference_proofs[i].get('proof_contract')!='reference_catalog_identity_raw_OCR_location' for i in candidates):return no('missing_or_uncertified_reference_title_row')
    # One physical reference per candidate; neither duplicate catalogue photos
    # nor repeated query transforms can provide independent votes.
    if any(reference_proofs[i].get('catalog_index')!=i or reference_proofs[i].get('catalog_slug')!=catalog.references[i].get('slug') or reference_proofs[i].get('source_sha256')!=catalog.references[i].get('sha256') or not reference_proofs[i].get('catalog_sha256') or not reference_proofs[i].get('box') for i in candidates):return no('unbound_catalog_row_reference_or_crop_proof')
    hashes=[reference_proofs[i].get('source_sha256') for i in candidates]
    if None in hashes or len(set(hashes))!=len(hashes):return no('duplicate_or_unbound_physical_reference')
    if any(i not in scores or not math.isfinite(float(scores[i])) for i in candidates):return no('missing_or_nonfinite_model_score')
    ranked=sorted(candidates,key=lambda i:(-float(scores[i]),list(map(int,base_order)).index(i)))
    winner,runner=ranked[:2];best=float(scores[winner]);margin=best-float(scores[runner]);flags.update(candidate_scores={str(i):float(scores[i]) for i in candidates},winner=winner,similarity=best,margin=margin)
    if best<MIN_SIMILARITY or margin<MIN_MARGIN:return no('unqualified_similarity_or_margin')
    if winner==head:return no('current_c08_head_already_verified')
    if contradicted(catalog.rows[winner],query):return no('winner_conflicts_with_trusted_c08_evidence')
    if winner not in list(map(int,result)):return no('winner_outside_existing_original_top20')
    selected=np.asarray([winner]+[int(i) for i in result if int(i)!=winner]);flags.update(title_override=True,selected_candidate=winner,reason='independent_complete_title_region_verified',original_top20_preserved=set(map(int,selected[:20]))==set(map(int,base_order[:20])))
    return selected,flags
