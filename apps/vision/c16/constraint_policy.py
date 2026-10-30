"""Catalog-only family identification and cross-view/text evidence decisions.

No query ID/path, image lookup, accepted answer, or wine-specific exception.
Three visual votes are the existing whole, bottle, and label views. OCR
verification is limited to the visual shortlist and cannot invent candidates.
"""
import numpy as np
from gram_ocr import norm, attributes

STOP = set(norm('вино белое красное розовое сухое полусухое сладкое полусладкое игристое выдержанное резерв reserve selection collection brut extra premium classic').split())

def rank(scores):
    # Preserve the original SIMPLE84 tie order as well as unequal-score order.
    return np.argsort(-scores)

def promote(order, winner):
    return np.asarray([int(winner)] + [int(i) for i in order if i != winner])

class CatalogFamilies:
    def __init__(self, references, attributes):
        self.attributes = attributes
        grape_words = set(' '.join(attributes.vocab).split())
        self.producer = [norm(r.get('winery', '')) for r in references]
        self.line = [set(t for t in norm(r.get('title', '')).split()
                         if len(t) >= 4 and not t.isdigit()) - STOP - grape_words
                     for r in references]

    def same(self, a, b):
        a, b = int(a), int(b)
        return bool(self.producer[a] and self.producer[a] == self.producer[b]
                    and self.line[a] & self.line[b])

    def shortlist(self, baseline, order):
        return [int(i) for i in order[:5] if i == baseline or self.same(baseline, i)]

def visual_decision(base_order, view_scores, families, view_boxes=None):
    """Keep original ranking, except two agreeing views in one catalog family.

    Absolute cosine scores/margins from different galleries are not compared.
    The third (label) view has one vote, independent of how large its margin is.
    Reordering preserves the original Top5 membership.
    """
    order = np.asarray(base_order).copy()
    votes = [int(rank(s)[0]) for s in view_scores]
    # The same physical crop may be reused by two named branches. It is one
    # observation, even if projected into different galleries. Conflicting
    # winners for the same pixels provide no unambiguous visual vote.
    groups = {}
    for n, vote in enumerate(votes):
        key = tuple(view_boxes[n]) if view_boxes is not None else (n,)
        groups.setdefault(key, set()).add(vote)
    distinct_votes = [next(iter(heads)) for heads in groups.values() if len(heads) == 1]
    winner = None
    for candidate in dict.fromkeys(distinct_votes):
        if distinct_votes.count(candidate) >= 2:
            winner = candidate
            break
    changed = bool(winner is not None and winner != order[0]
                   and winner in order[:5] and families.same(winner, order[0]))
    # Full frame and padded bottle are correlated views. Their majority cannot
    # resolve a conflicting coarse product class by itself. Colour-changing
    # proposals require explicit text verification in the separate evidence step.
    color_conflict = False
    if changed:
        base_color = families.attributes.rows[int(order[0])]['color']
        proposed_color = families.attributes.rows[int(winner)]['color']
        color_conflict = bool(base_color and proposed_color and not base_color & proposed_color)
    return (promote(order, winner) if changed and not color_conflict else order), {
        'visual_votes': votes, 'distinct_view_votes': distinct_votes, 'consensus_override': changed and not color_conflict,
        'visual_proposal': winner, 'blocked_color_conflict': color_conflict,
        'proposal_reason': 'text_required_for_color_conflict' if color_conflict else 'same_family_visual_agreement'}

def needs_text(base_order, base_scores, votes, families):
    head = int(base_order[0])
    group = families.shortlist(head, base_order)
    conflict = any(v != head and families.same(head, v) for v in votes)
    ambiguous = (base_scores[base_order[0]] - base_scores[base_order[1]] <= .03)
    attribute_variants = any(len({frozenset(families.attributes.rows[i][key]) for i in group}) > 1
                             for key in ('grape', 'color', 'sugar'))
    return len(group) > 1 and attribute_variants and (conflict or ambiguous)

def query_attributes(catalog, text):
    # The original helper erases conflicting colours/sweetness. Preserve them
    # so the verification layer can explicitly reject contradictory OCR evidence.
    query = catalog.query(text)
    query['color'], query['sugar'] = attributes(text)
    return query

def text_decision(base_order, current_order, pass_words, families):
    """Unique positive attribute evidence in original Top5, within one family.

    Require confidence>=90 once, or confidence>=80 in two OCR passes.
    Multi-pass text is correlated evidence, not independent probabilities.
    No relaxation of spelling/attributes based on a specific query.
    """
    catalog = families.attributes
    grouped = families.shortlist(int(base_order[0]), base_order)
    evidence = []
    reliable = []
    for words in pass_words:
        strong = [w for w in words if w['confidence'] >= 80]
        query = query_attributes(catalog, ' '.join(w['text'] for w in strong))
        evidence.append(query)
        reliable.append(query_attributes(catalog, ' '.join(w['text'] for w in words if w['confidence'] >= 90)))
    query = {}
    for key in ('grape', 'color', 'sugar'):
        once = set().union(*(q[key] for q in reliable))
        repeated = set().union(*(q[key] for q in evidence))
        repeated = {v for v in repeated if sum(v in q[key] for q in evidence) >= 2}
        query[key] = once | repeated
    # A confident discriminating colour or sweetness is valid evidence even
    # when no grape is printed. Contradictory readings cannot override retrieval.
    if any(len(values) > 1 for values in query.values()):
        return np.asarray(current_order), {'text_override': False, 'reason': 'contradictory_reliable_attributes',
                                          'query': {k: sorted(v) for k, v in query.items()}}
    if not any(query.values()):
        return np.asarray(current_order), {'text_override': False, 'reason': 'no_reliable_attributes'}
    matches = []
    for i in grouped:
        row = catalog.rows[i]
        # Unknown catalogue fields provide neither positive support nor conflict.
        if any(q and row[k] and not q & row[k] for k, q in query.items()):
            continue
        matches.append(i)
    if len(matches) != 1:
        return np.asarray(current_order), {'text_override': False, 'reason': 'no_unique_catalog_match'}
    winner = matches[0]
    if not any(q and catalog.rows[winner][k] & q for k, q in query.items()):
        return np.asarray(current_order), {'text_override': False, 'reason': 'catalog_attributes_unknown'}
    changed = winner != int(current_order[0])
    return promote(current_order, winner), {'text_override': changed,
        'reason': 'unique_catalog_attribute_match', 'query': {k: sorted(v) for k, v in query.items()}}
