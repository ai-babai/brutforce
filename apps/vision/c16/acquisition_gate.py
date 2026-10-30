"""Measured resource-abort nomination only, no ranking or lexical evidence."""
RESOURCE_ABORTS={'foreground_limit','component_limit','merge_pair_limit'}
def plan(base_order,current_order,query,raw_query,families,character_result,prior_overrides=None):
    flags={'requested':False,'budget_ms':1500,'max_calls':4,'ranking_mutation':False,'language':'rus+eng'}
    if any((prior_overrides or {}).values()):return dict(flags,reason='prior_verified_override_preserved')
    if any(len(set(v))>1 for v in query.values()) or len(set(raw_query.get('grape',())))>1:return dict(flags,reason='conflicting_or_rawblend_uncertainty')
    stats=character_result.get('proposal_budget',{})
    if not stats.get('aborted') or stats.get('abort_reason') not in RESOURCE_ABORTS or character_result.get('calls_attempted',0)!=0:return dict(flags,reason='not_measured_precall_resource_abort')
    if not len(base_order) or not len(current_order):return dict(flags,reason='empty_original_proposal')
    group=families.candidates(int(base_order[0]),base_order);rows=families.attributes.rows
    if int(current_order[0]) not in group or len(group)<2:return dict(flags,reason='no_existing_semantic_variant_group')
    varying=[k for k in ('grape','color') if not query.get(k) and len({frozenset(rows[i][k]) for i in group if rows[i][k]})>1]
    if not varying:return dict(flags,reason='no_unresolved_grape_or_color_variation')
    return dict(flags,requested=True,reason='independent_local_rows_after_measured_global_noise_abort',missing_fields=varying,original_top20=[int(i) for i in base_order[:20]],prior_resource_abort=stats,prior_wall_ms=character_result.get('wall_ms'),correlation='one physical row across transformations, no independent80votes')
