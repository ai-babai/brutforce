"""Original CASCADE84 rules plus the already frozen fullframe margin gate."""
import numpy as np

CASCADE84 = dict(name='cascade84_batch32_query_legacy_label_gallery', kind='cascade',
                base=dict(kind='gate', view='central_pad25', floor=.03),
                candidate=dict(kind='gate', view='central_pad10', gallery='legacy_label',
                               floor=0, reciprocal_top5=True))
CASCADE_SIMPLE84 = dict(name='simple84_fullframe_gate_then_original_cascade84',
                       kind='cascade_simple84', visual=CASCADE84)
EXECUTION = dict(full_margin_crop_gate=.05, persistent_detector_prefire=True,
                 detector_workers=1, max_siglip_encodes=3)

def top_margin(scores):
    rank = np.argsort(-scores)
    return float(scores[rank[0]] - scores[rank[1]])

def needs_crops(full_scores):
    return top_margin(full_scores) <= .05

def cascade84(full_scores, pad25_scores, legacy_pad10_scores):
    """Same pad25/full gate .03, then reciprocal legacy-label pad10 gate 0."""
    full_rank, crop_rank = np.argsort(-full_scores), np.argsort(-pad25_scores)
    switch = (full_rank[0] in crop_rank[:5] and
              top_margin(pad25_scores) >= top_margin(full_scores) and
              top_margin(pad25_scores) >= .03)
    base = pad25_scores if switch else full_scores
    base_rank, label_rank = np.argsort(-base), np.argsort(-legacy_pad10_scores)
    reciprocal = base_rank[0] in label_rank[:5] and label_rank[0] in base_rank[:5]
    switch = (reciprocal and top_margin(legacy_pad10_scores) >= top_margin(base)
              and top_margin(legacy_pad10_scores) >= 0)
    return legacy_pad10_scores if switch else base
