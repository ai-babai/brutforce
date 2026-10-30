"""Upper SigLIP nominates; same-view artwork verifies versus current head.

Only precall resource-aborted, semantically unresolved originalTop5 proposals.
Unknown metadata remains visual competition; no hue-global-uniqueness claim,
wine-colour inference, threshold change, independent-vote or absence evidence.
"""
import math
import numpy as np
from chromatic_artwork import BINS, VERSION as DESCRIPTOR_VERSION

VERSION = 'upper-artwork-pairwise-v2-positive-resource-signature-preserved'
MINIMUM_SIMILARITY = .70
PAIRWISE_MARGIN = .05
RESOURCE_ABORTS = {'foreground_limit', 'component_limit', 'merge_pair_limit'}
GEOMETRY_VERSION = 'source_bound_upper_bottle_visual_top35-v6-rounding-fragments'
STRONG_OVERRIDES = ('text_override','title_override','semantic_expansion_override',
                    'coherent_support_override','local_grape_override',
                    'resource_field_override','positive_signature_override','resource_signature_override')


def histogram(descriptor, role):
    if (descriptor.get('version') != DESCRIPTOR_VERSION or
            descriptor.get('role') != role or descriptor.get('accepted') is not True):
        raise ValueError('Wrong or unready source artwork contract')
    h = np.asarray(descriptor.get('histogram'), dtype=float)
    if h.shape != (BINS,) or not np.isfinite(h).all() or np.any(h < 0):
        raise ValueError('Invalid observed source artwork histogram')
    total = float(h.sum())
    empty = role == 'reference' and descriptor.get('empty_reference_chromatic_histogram_observed') is True
    if not (abs(total - 1.) <= 1e-6 or (empty and total == 0)):
        raise ValueError('Nonprobability source artwork histogram')
    if role == 'query' and float(descriptor.get('chromatic_area_fraction', 0)) < .15:
        raise ValueError('Query chromatic area below unchanged prerequisite')
    if role == 'reference' and float(descriptor.get('contrast_q95_q05', 0)) < 35:
        raise ValueError('Reference source quality below unchanged prerequisite')
    return h


def decide(base_order, current_order, nomination, upper_result, reliable_query,
           raw_query, character_result, prior_overrides, query_artwork,
           reference_artwork):
    base = list(map(int, base_order[:20])); current = list(map(int, current_order))
    flags = {'override':False, 'version':VERSION,
             'thresholds':{'upper_nomination_minimum_cosine':MINIMUM_SIMILARITY,
                           'artwork_minimum_similarity':MINIMUM_SIMILARITY,
                           'artwork_current_head_margin':PAIRWISE_MARGIN},
             'correlation_group':'same_actual_upper_RGB_crop',
             'independent_votes':False, 'wine_attribute_inference':False,
             'global_hue_uniqueness_asserted':False,
             'unknown_metadata_excluded':False, 'upper_scores':{}, 'artwork_scores':{}}
    def stop(reason):
        return current, dict(flags, reason=reason)
    if not base or len(set(base)) != len(base) or set(current[:20]) != set(base):
        return stop('invalid_actual_originalTop20_scope')
    if any(bool(v) for v in reliable_query.values()):
        return stop('trusted_semantic_evidence_preserved')
    if len(set(raw_query.get('grape', ()))) > 1:
        return stop('raw_multigrape_uncertainty_preserved')
    if any(prior_overrides.get(k) for k in STRONG_OVERRIDES):
        return stop('prior_independent_override_preserved')
    stats = character_result.get('proposal_budget', {})
    if not (stats.get('aborted') is True and stats.get('abort_reason') in RESOURCE_ABORTS and
            character_result.get('calls_attempted') == 0):
        return stop('not_measured_precall_resource_abort')
    if not nomination.get('requested') or upper_result.get('accepted') is not True:
        return stop('no_source_verified_upper_nomination')
    required = list(map(int, nomination.get('required_contenders', ())))
    scores = upper_result.get('scores', {}); proofs = upper_result.get('reference_proofs', {})
    identity = upper_result.get('expected_identity', {})
    geometry = upper_result.get('query_geometry', {})
    if (len(required) < 2 or len(set(required)) != len(required) or
            not set(required) <= set(base) or current[0] not in required or
            set(scores) != set(required) or set(proofs) != set(required) or
            set(reference_artwork) != set(required)):
        return stop('every_compatible_unknown_reference_must_participate')
    binding_keys = ('catalog_sha256','encoder_binding_sha256','gallery_manifest_sha256')
    if (geometry.get('accepted') is not True or geometry.get('version') != GEOMETRY_VERSION or
            not all(identity.get(k) for k in binding_keys) or
            geometry.get('source_sha256') != identity.get('query_source_sha256') or
            not geometry.get('source_sha256') or
            query_artwork.get('crop_RGB_sha256') != geometry.get('upper_rgb_crop_sha256')):
        return stop('query_source_crop_or_encoder_identity_mismatch')
    seen = set()
    try:
        q = histogram(query_artwork, 'query')
        for i in required:
            p = proofs[i]; row = identity.get('reference_rows', {}).get(i, {})
            if (not row or any(p.get(k) != row.get(k) for k in ('slug','reference_sha256')) or
                    any(p.get(k) != identity[k] for k in binding_keys) or
                    p.get('catalog_index') != i or not p.get('slug') or not p.get('reference_sha256') or
                    p.get('geometry', {}).get('accepted') is not True or
                    p.get('geometry', {}).get('version') != GEOMETRY_VERSION or
                    p.get('geometry', {}).get('source_sha256') != p['reference_sha256'] or
                    p.get('geometry', {}).get('upper_rgb_crop_sha256') != p.get('view_crop_sha256') or
                    reference_artwork[i].get('crop_RGB_sha256') != p.get('view_crop_sha256') or
                    p.get('score_row_binding') != {k:p.get(k) for k in
                                                   ('catalog_index','slug','reference_sha256','view_crop_sha256')}):
                return stop('all_score_and_artwork_reference_bindings_required')
            if p['view_crop_sha256'] in seen:
                return stop('duplicate_source_crop_identity_unknown')
            seen.add(p['view_crop_sha256'])
            v = float(scores[i])
            if not math.isfinite(v):
                return stop('nonfinite_upper_model_score')
            h = histogram(reference_artwork[i], 'reference')
            flags['upper_scores'][str(i)] = v
            flags['artwork_scores'][str(i)] = float(np.sqrt(q*h).sum())
    except (TypeError, ValueError, KeyError) as error:
        return stop('invalid_observed_artwork_or_binding: '+str(error))
    maximum = max(float(scores[i]) for i in required)
    winners = [i for i in required if float(scores[i]) == maximum]
    if len(winners) != 1 or maximum < MINIMUM_SIMILARITY:
        return stop('upper_visual_nomination_not_unique_positive')
    winner = winners[0]; head = current[0]
    flags.update(nominated_index=winner, current_head=head,
                 complete_compatible_reference_count=len(required),
                 upper_nomination_cosine=maximum,
                 scope='source_bound_originalTop20_all_compatible_upper_scored')
    if winner not in base[:5]:
        return stop('pairwise_nomination_outside_originalTop5')
    if winner == head:
        return stop('current_head_already_upper_nomination')
    positive = flags['artwork_scores'][str(winner)]
    head_similarity = flags['artwork_scores'][str(head)]
    margin = positive - head_similarity
    flags.update(nominated_artwork_similarity=positive,
                 current_head_artwork_similarity=head_similarity,
                 pairwise_artwork_margin=margin,
                 resource_abort_provenance=stats,
                 all_other_artwork_scores_retained_not_global_rank_or_exclusion=True)
    if positive < MINIMUM_SIMILARITY or margin < PAIRWISE_MARGIN:
        return stop('positive_current_head_comparison_not_verified')
    selected = [winner] + [i for i in current if i != winner]
    return selected, dict(flags, override=True, originalTop20_membership_preserved=True,
                         reason='unique_upper_visual_proposal_positively_verified_against_current_head_same_view')
