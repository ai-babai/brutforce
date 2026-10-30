"""Positive independent structural view verifies originalTop20 nominations.
No predicted closure type, color, grape, producer or query special rules.
"""
import math
from candidate_policy import contradicted,KEYS
MINIMUM_COSINE=0.70;RUNNERUP_MARGIN=0.05
RESOURCE_ABORTS={'foreground_limit','component_limit','merge_pair_limit'}

def nominate(base_order,current_order,query,raw_query,families,character_result,prior_overrides=None):
    base=[int(i) for i in base_order[:20]];current=[int(i) for i in current_order];q={k:set(query.get(k,())) for k in KEYS};raw={k:set(raw_query.get(k,())) for k in KEYS};prior=prior_overrides or {}
    flags={'requested':False,'original_top20':base,'query':{k:sorted(v) for k,v in q.items()},'scope':'existing_originalTop20_structural_family','thresholds':{'minimum_cosine':MINIMUM_COSINE,'runnerup_margin':RUNNERUP_MARGIN},'wine_attribute_inference_from_neck':False}
    def stop(reason):return dict(flags,reason=reason)
    if not base or not current or len(set(base))!=len(base) or set(current[:20])!=set(base):return stop('invalid_original_scope')
    if any(len(v)>1 for v in q.values()) or len(raw['grape'])>1:return stop('conflicting_or_rawblend_uncertainty')
    if any(prior.get(k) for k in ('title_override','semantic_expansion_override','coherent_support_override','local_grape_override')):return stop('prior_independent_verification_preserved')
    group=families.candidates(base[0],base);rows=families.attributes.rows
    if current[0] not in group:return stop('current_head_outside_structural_family')
    fields={k for k,v in q.items() if v};compatible=[i for i in group if not contradicted(rows[i],q)];unknown=[i for i in compatible if any(not rows[i][k] for k in (fields or set(KEYS)))]
    if hasattr(families,'line'):
        unknown.extend(i for i in base if i not in group and families.producer[i]==families.producer[base[0]] and (not families.line[i] or not families.line[base[0]]) and not contradicted(rows[i],q))
    flags.update(required_contenders=compatible,unknown_metadata_or_line=sorted(set(unknown)),rejected_known_contradictions=[i for i in group if i not in compatible])
    # Metadata unknown blocks semantic uniqueness, not independent visual
    # competition. Retain unknown-line rows too; all must have certified
    # source geometry and be actually scored. Missing reference still blocks.
    compatible=list(dict.fromkeys(compatible+unknown))
    flags['required_contenders']=compatible
    flags['unknown_metadata_retained_as_visual_competitors']=sorted(set(unknown))
    if len(compatible)<2:return stop('no_unresolved_originalTop20_ambiguity')
    stats=character_result.get('proposal_budget',{});resource=bool(stats.get('aborted') and stats.get('abort_reason') in RESOURCE_ABORTS and character_result.get('calls_attempted',0)==0)
    if not fields and not resource:return stop('neither_trusted_field_nor_measured_precall_resource_abort')
    # Top5 compatibility filtering is a nomination, not full scope verification.
    # Reliable fields remain binding; it can be refined only while fullTop20
    # compatibility stays nonunique. No positively verified prior result changed.
    return dict(flags,requested=True,reason='independent_upper_bottle_view_can_verify_unresolved_original_scope',prior_Top5_text_nomination_refinable=bool(prior.get('text_override')),resource_abort_nomination=resource,resource_abort_provenance=stats if resource else None)

def select(current_order,nomination,query_geometry,reference_proofs,scores,expected_identity):
    current=[int(i) for i in current_order];flags={'override':False,'nomination':nomination,'scores':{},'thresholds':{'minimum_cosine':MINIMUM_COSINE,'runnerup_margin':RUNNERUP_MARGIN},'attribute_inference':False}
    def stop(reason):return current,dict(flags,reason=reason)
    if not nomination.get('requested'):return stop('no_certified_nomination')
    needed=nomination['required_contenders']
    if not query_geometry.get('accepted') or query_geometry.get('version')!='source_bound_upper_bottle_visual_top35-v6-rounding-fragments':return stop('query_upper_geometry_uncertified')
    binding_keys=('catalog_sha256','encoder_binding_sha256','gallery_manifest_sha256')
    if not all(expected_identity.get(k) for k in binding_keys) or not expected_identity.get('query_source_sha256') or not expected_identity.get('reference_rows'):return stop('missing_bound_query_catalog_encoder_gallery_identity')
    if query_geometry.get('source_sha256')!=expected_identity['query_source_sha256']:return stop('query_source_identity_mismatch')
    if set(reference_proofs)!=set(needed) or set(scores)!=set(needed):return stop('not_all_compatible_originalTop20_references_scored')
    seen=set()
    for i in needed:
        p=reference_proofs[i]
        source_row=expected_identity['reference_rows'].get(i,expected_identity['reference_rows'].get(str(i),{}))
        if not source_row or any(p.get(k)!=source_row.get(k) for k in ('slug','reference_sha256')):return stop('reference_not_actual_catalog_row_identity')
        if any(p.get(k)!=expected_identity[k] for k in binding_keys) or p.get('catalog_index')!=i or not p.get('slug') or not p.get('reference_sha256') or not p.get('view_crop_sha256') or not p.get('geometry',{}).get('accepted') or p.get('geometry',{}).get('version')!=query_geometry['version'] or p.get('geometry',{}).get('source_sha256')!=p.get('reference_sha256'):return stop('reference_score_identity_or_geometry_mismatch')
        if p.get('score_row_binding')!={'catalog_index':i,'slug':p['slug'],'reference_sha256':p['reference_sha256'],'view_crop_sha256':p['view_crop_sha256']}:return stop('model_score_not_bound_to_source_reference_crop')
        if p['view_crop_sha256'] in seen:return stop('duplicate_reference_neck_identity_unknown')
        seen.add(p['view_crop_sha256']);value=float(scores[i])
        if not math.isfinite(value):return stop('nonfinite_model_score')
        flags['scores'][str(i)]=value
    ranked=sorted(needed,key=lambda i:(-float(scores[i]),nomination['original_top20'].index(i)));winner=ranked[0];best=float(scores[winner]);margin=best-float(scores[ranked[1]])
    flags.update(best_cosine=best,runnerup_margin=margin,selected_candidate=winner,complete_compatible_reference_count=len(needed))
    if best<MINIMUM_COSINE or margin<RUNNERUP_MARGIN:return stop('predeclared_visual_verification_insufficient')
    if winner not in current or set(current[:20])!=set(nomination['original_top20']):return stop('verified_winner_or_output_outside_original_scope')
    return [winner]+[i for i in current if i!=winner],dict(flags,override=winner!=current[0],reason='positive_independent_upper_bottle_view_unique_among_all_compatible_originalTop20',original_top20_preserved=True)
