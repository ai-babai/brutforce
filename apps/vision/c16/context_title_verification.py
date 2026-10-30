"""Additive positive context-title image verification over original proposals."""
import math
import numpy as np
from candidate_policy import canonical_norm
from title_reacquisition import nominate, grape_relation, STRONG

VERSION='context-title-verification-draft-v1-070-005'
MIN_SIMILARITY=.70
MIN_MARGIN=.05


def prior_observation_failed(flags):
    if flags.get('ocr_errors'):return True
    for key in ('character_ocr','semantic_acquisition','title_verification','resource_field_verification','upper_view_verification','local_grape_verification'):
        value=flags.get(key,{})
        if isinstance(value,dict) and (value.get('errors') or value.get('acquisition',{}).get('errors')):return True
    return False


def gate(base_order,current_order,query,families,references,flags=None,reference_ready=None,raw_multi_grape=False):
    if prior_observation_failed(flags or {}):
        return {'requested':False,'reason':'failed_previous_observation','ranking_mutation':False}
    if raw_multi_grape:
        return {'requested':False,'reason':'raw_blend_uncertainty','ranking_mutation':False}
    return nominate(base_order,current_order,families.attributes.rows,families.producer,
                    [r.get('title','') for r in references],families.attributes.vocab,
                    canonical_norm,query,flags,reference_ready)


def completed_observation(acquisition):
    if acquisition.get('errors') or any(c.get('errors') for c in acquisition.get('calls',[])):
        return False
    budget=acquisition.get('budget',{})
    if budget.get('exhausted') or acquisition.get('budget_exhausted') or acquisition.get('partial_observations'):
        return False
    attempted=acquisition.get('calls_attempted');completed=acquisition.get('calls_completed')
    if attempted is not None or completed is not None:
        if attempted is None or completed is None or attempted!=completed:return False
    return True


def decide(base_order,current_order,query,families,references,acquisition,scores,
           reference_proofs,flags=None,raw_multi_grape=False,catalog_sha256=None):
    result=np.asarray(current_order).copy();flags=flags or {}
    details={'version':VERSION,'context_title_override':False,'title_override':False,
             'minimum_similarity':MIN_SIMILARITY,'minimum_margin':MIN_MARGIN,
             'scope':'same_producer_related_variety_existing_originalTop20',
             'generic_variety_is_not_specific_semantic_proof':True,
             'same_physical_row_correlated_evidence':True}
    def no(reason):return result,dict(details,reason=reason)
    if not len(base_order) or not len(result):return no('empty_rankings')
    if any(flags.get(k) for k in STRONG):return no('preserve_existing_independent_override')
    if prior_observation_failed(flags):return no('failed_old_OCR_observation')
    query={k:set(query.get(k,())) for k in ('grape','color','sugar')}
    if raw_multi_grape or any(len(v)>1 for v in query.values()):return no('raw_blend_or_trusted_conflict')
    if not completed_observation(acquisition):return no('incomplete_context_observation')
    if not acquisition.get('accepted') or acquisition.get('role')!='following_product_title_row' or acquisition.get('proof_contract')!='query_reliable_whole_grape':
        return no('missing_positive_whole_query_anchor_and_title_role')
    anchor=set(acquisition.get('trusted_grapes',()))
    if len(anchor)!=1:return no('missing_or_multiple_whole_grape_anchor')
    if query['grape'] and grape_relation(query['grape'],anchor) not in ('exact','specificity_uncertainty'):
        return no('whole_anchor_conflicts_with_trusted_variety')
    # Preserve compound query as actually observed; never union its generic
    # prefix into a fictitious blend or use generic evidence as subtype proof.
    observed_query={k:set(v) for k,v in query.items()}
    if not observed_query['grape']:observed_query['grape']=anchor
    plan=gate(base_order,current_order,observed_query,families,references,flags,
              lambda i:i in reference_proofs and reference_proofs[i].get('accepted'),raw_multi_grape)
    details['nomination']=plan;details['actual_trusted_query']={k:sorted(v) for k,v in query.items()};details['whole_anchor']=sorted(anchor)
    if not plan.get('requested'):return no(plan['reason'])
    if plan.get('unknown'):return no('compatible_unknown_catalogue_context_or_metadata')
    candidates=plan['required_contenders'];original=list(map(int,base_order[:20]));current=list(map(int,result[:20]))
    if len(set(original))!=len(original) or set(current)!=set(original):return no('original_proposal_membership_not_preserved')
    if int(result[0]) not in candidates or len(candidates)<2:return no('current_head_not_in_complete_comparison')
    if not catalog_sha256:return no('missing_expected_catalogue_digest')
    source_hashes=[]
    for i in candidates:
        p=reference_proofs.get(i,{})
        if not p.get('accepted') or not completed_observation(p) or p.get('role')!='following_product_title_row' or p.get('proof_contract')!='reference_catalog_identity_raw_OCR_location':
            return no('missing_or_incomplete_reference_title_proof')
        if (p.get('catalog_index')!=i or p.get('catalog_slug')!=references[i].get('slug')
                or p.get('source_sha256')!=references[i].get('sha256') or p.get('catalog_sha256')!=catalog_sha256
                or not p.get('box') or not p.get('following_row') or not p.get('anchor')):
            return no('unbound_reference_identity_or_physical_row')
        location=set(p.get('catalog_grapes',()))
        if grape_relation(location,anchor) not in ('exact','specificity_uncertainty'):
            return no('reference_location_anchor_not_related_whole_variety')
        source_hashes.append(p['source_sha256'])
    if None in source_hashes or len(set(source_hashes))!=len(source_hashes):return no('duplicate_physical_reference_uncertainty')
    if any(i not in scores or not math.isfinite(float(scores[i])) for i in candidates):return no('missing_or_nonfinite_required_score')
    ranked=sorted(candidates,key=lambda i:(-float(scores[i]),original.index(i)))
    winner,runner=ranked[:2];best=float(scores[winner]);margin=best-float(scores[runner])
    details.update(candidate_scores={str(i):float(scores[i]) for i in candidates},winner=winner,similarity=best,margin=margin)
    if best<MIN_SIMILARITY or margin<MIN_MARGIN:return no('unqualified_similarity_or_margin')
    if winner==int(result[0]):return no('current_head_already_verified')
    selected=np.asarray([winner]+[int(i) for i in result if int(i)!=winner])
    details.update(context_title_override=True,title_override=True,selected_candidate=winner,
                   original_top20_preserved=set(map(int,selected[:20]))==set(original),
                   reason='positive_complete_context_title_image_verified')
    return selected,details
