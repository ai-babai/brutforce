"""Catalog semantic compatibility over the original visual Top5.

No image identity, evaluation target, model, or producer exception. OCR evidence
uses the frozen >=90 once / >=80 in two passes rule. Visual voting is frozen V6.
"""
import numpy as np
from gram_ocr import norm, attributes
from constraint_policy import CatalogFamilies as V6Families, visual_decision, rank, promote

KEYS = ('grape', 'color', 'sugar')
# Canonical catalog spellings for multilingual grape names. No short codes,
# fuzzy matching, image-dependent interpretation, or confidence relaxation.
GRAPE_ALIASES = {
    'viognier': 'vione', 'gris': 'gri', 'blanc': 'blan', 'franc': 'fran',
    'grigio': 'gridzhio', 'malbec': 'malbek', 'malvasia': 'malvaziya',
    'gewurztraminer': 'gevyurtstraminer', 'grenache': 'grenash',
    'mourvedre': 'murvedr', 'carmenere': 'karmener', 'colombard': 'kolombar',
    'corvina': 'korvina', 'sangiovese': 'sandzhoveze', 'tempranillo': 'tempranilo',
    'moscato': 'moskato', 'giallo': 'dzhallo', 'chenin': 'shenen',
    'semillon': 'semilon', 'roussanne': 'rusan', 'marsanne': 'marsan',
    'sylvaner': 'silvaner', 'solaris': 'solyaris', 'zweigelt': 'tsvaygelt',
}

def canonical_norm(text):
    return ' '.join(GRAPE_ALIASES.get(t, t) for t in norm(text).split())
# These are generic product/variety words, not producer identifiers. They only
# inform family uncertainty; OCR vocabulary and confidence remain frozen.
TITLE_GRAPES = set(canonical_norm('viognier gris malbec malvasia rkatsiteli saperavi aligote tempranillo mourvedre grenache marselan nebbiolo sangiovese moscato giallo zinfandel gewurztraminer traminer').split())
TITLE_STOP = set(norm('wine sparkling still вино белое красное розовое сухое полусухое сладкое полусладкое игристое выдержанное резерв reserve selection collection brut extra premium classic и and').split())
STRUCTURED_GROUPS = ('family_key', 'product_family', 'product_line', 'range', 'collection')

class CatalogFamilies(V6Families):
    """Named lines plus bounded uncertainty for plain varietal titles.

    A shared producer alone is insufficient: named lines must agree, or both
    rows must have no meaningful line name after removing variety/producer words.
    Compact varietal codes are only uncertain when catalog grape is known.
    Structured group keys take precedence when supplied by a future catalog.
    """
    def __init__(self, references, attributes):
        super().__init__(references, attributes)
        grape_words = set(' '.join(attributes.vocab).split()) | TITLE_GRAPES
        self.group_keys = [tuple((k, norm(r[k])) for k in STRUCTURED_GROUPS
                                 if r.get(k) and isinstance(r[k], (str, int)))
                           for r in references]
        self.kind = []
        self.generic = []
        for i, r in enumerate(references):
            tokens = set(canonical_norm(r.get('title', '')).split())
            producer_tokens = set(self.producer[i].split())
            residual = {t for t in tokens - producer_tokens - grape_words - TITLE_STOP
                        if not t.isdigit()}
            # A grape-only title or an explicitly catalogued short varietal code
            # has uncertain line membership; a named residual line never does.
            compact = bool(len(residual) == 1 and attributes.rows[i]['grape'] and
                           all(len(t) <= 2 for t in residual))
            self.generic.append(not residual or compact)
            self.line[i] = set() if compact else residual
            self.kind.append('sparkling' if tokens & {'igristoe', 'sparkling', 'bryut'} else '')

    def same(self, a, b):
        a, b = int(a), int(b)
        if a == b:
            return True
        if not self.producer[a] or self.producer[a] != self.producer[b]:
            return False
        ga, gb = dict(self.group_keys[a]), dict(self.group_keys[b])
        shared = set(ga) & set(gb)
        if shared:
            return all(ga[k] == gb[k] for k in shared)
        if self.kind[a] != self.kind[b]:
            return False
        if self.line[a] and self.line[a] == self.line[b]:
            return True
        return bool(self.generic[a] and self.generic[b] and
                    any(self.attributes.rows[a][k] for k in KEYS) and
                    any(self.attributes.rows[b][k] for k in KEYS))


def variant_keys(group, families):
    """Unknown values are uncertainty, never a measured semantic difference."""
    return [k for k in KEYS if len({frozenset(families.attributes.rows[i][k])
                                   for i in group if families.attributes.rows[i][k]}) > 1]


def needs_text(base_order, base_scores, votes, families):
    head = int(base_order[0])
    group = families.shortlist(head, base_order)
    variants = variant_keys(group, families)
    if len(group) < 2 or not variants:
        return False
    conflict = any(int(v) != head and families.same(head, int(v)) for v in votes)
    ambiguous = len(base_order) > 1 and base_scores[head] - base_scores[int(base_order[1])] <= .03
    # A multiway set of known semantic variants in the original Top5 is itself
    # meaningful uncertainty, even after crop fusion widens the visual margin.
    # This extra branch is bounded to existing crop requests and three siblings.
    multiway = len(group) >= 3 and any(sum(bool(families.attributes.rows[i][k])
                                         for i in group) >= 3 for k in variants)
    return bool(conflict or ambiguous or multiway)


def query_attributes(catalog, text):
    value = ' ' + canonical_norm(text) + ' '
    grape = {g for g in catalog.vocab if ' ' + g + ' ' in value}
    # A longer exact phrase subsumes its generic prefix (Sauvignon Blanc vs
    # Sauvignon); two distinct grape phrases remain conflicting evidence.
    grape = {g for g in grape if not any(g != h and ' ' + g + ' ' in ' ' + h + ' '
                                        for h in grape)}
    query = dict(grape=grape)
    query['color'], query['sugar'] = attributes(text)
    return query


def reliable_query(pass_words, catalog):
    evidence, reliable = [], []
    for words in pass_words:
        evidence.append(query_attributes(catalog, ' '.join(w['text'] for w in words if w['confidence'] >= 80)))
        reliable.append(query_attributes(catalog, ' '.join(w['text'] for w in words if w['confidence'] >= 90)))
    query = {}
    for key in KEYS:
        once = set().union(*(q[key] for q in reliable))
        candidates = set().union(*(q[key] for q in evidence))
        repeated = {v for v in candidates if sum(v in q[key] for q in evidence) >= 2}
        query[key] = once | repeated
    return query


def contradicted(row, query):
    return any(values and row[key] and not values & row[key]
               for key, values in query.items())


def raw_query(pass_words, catalog):
    """Exact full-token catalog attributes, without assigning them reliability.

    This is secondary corroboration/uncertainty only. The supplied OCR words
    retain their measured confidences; no fuzzy spellings or partial aliases.
    """
    queries = [query_attributes(catalog, ' '.join(str(w['text']) for w in words))
               for words in pass_words]
    return {key: set().union(*(q[key] for q in queries)) for key in KEYS}


def coherent_support(base_order, legacy_order, coherent_order, pass_words, families):
    """Verify a current-gallery nomination; default to the legacy proposal.

    The caller supplies a nomination made by distinct physical visual views.
    Raw OCR is only an independent exact varietal corroboration. It cannot
    promote a candidate alone or reject a candidate as reliable contradiction.
    """
    original = [int(i) for i in base_order[:5]]
    legacy = np.asarray(legacy_order).copy()
    coherent = np.asarray(coherent_order)
    raw = raw_query(pass_words, families.attributes)
    reliable = reliable_query(pass_words, families.attributes)
    flags = dict(coherent_support_override=False,
                 raw_query={k: sorted(v) for k,v in raw.items()},
                 reliable_query={k: sorted(v) for k,v in reliable.items()},
                 support_source='current_gallery_nomination_plus_exact_raw_grape',
                 raw_words=pass_words)
    def reject(reason):
        return legacy, dict(flags, reason=reason)
    if not original or not len(legacy) or not len(coherent):
        return reject('empty_order')
    if set(int(i) for i in legacy[:5]) != set(original) or set(int(i) for i in coherent[:5]) != set(original):
        return reject('original_top5_membership_violation')
    nominee, base = int(coherent[0]), original[0]
    flags['coherent_nominee'] = nominee
    if nominee == int(legacy[0]):
        return reject('legacy_already_selected_nominee')
    if nominee not in original:
        return reject('nominee_outside_original_top5')
    if not families.producer[base] or families.producer[nominee] != families.producer[base] or not families.same(base, nominee):
        return reject('nominee_outside_structural_family')
    if len(raw['grape']) != 1:
        return reject('raw_grape_not_single_exact_variety')
    if any(len(values) > 1 for values in reliable.values()):
        return reject('contradictory_reliable_attributes')
    row = families.attributes.rows[nominee]
    if contradicted(row, reliable):
        return reject('nominee_contradicts_reliable_attributes')
    group = families.shortlist(base, base_order)
    known = [i for i in group if families.attributes.rows[i]['grape']]
    supported = [i for i in known if raw['grape'] & families.attributes.rows[i]['grape']]
    flags.update(known_family_candidates=known, raw_grape_supported_candidates=supported)
    if supported != [nominee]:
        return reject('raw_grape_does_not_uniquely_identify_nominee')
    flags.update(coherent_support_override=True, selected_candidate=nominee,
                 reason='distinct_gallery_nomination_verified_by_exact_raw_variety')
    return promote(legacy, nominee), flags


def text_decision(base_order, current_order, pass_words, families, character_query=None):
    """Filter reliable contradictions independently of unique positive support.

    Unknown catalog fields remain compatible. If the current head contradicts
    reliable OCR, select the earliest compatible row in the original Top5,
    including when several rows survive. Never enlarge original Top5 membership.
    """
    original = [int(i) for i in base_order[:5]]
    current = np.asarray(current_order).copy()
    query = reliable_query(pass_words, families.attributes)
    # Character evidence is an explicit separate source, never a fabricated OCR word.
    if character_query:
        for key,values in character_query.items():
            if key not in KEYS: raise ValueError('Unknown character evidence field')
            query[key] |= set(values)
    flags = {'text_override': False, 'query': {k: sorted(v) for k, v in query.items()},
             'character_query': {k: sorted(v) for k,v in (character_query or {}).items()}}
    raw = raw_query(pass_words, families.attributes)
    flags['raw_query'] = {k: sorted(v) for k,v in raw.items()}
    # Multiple exact raw varietal phrases are blend uncertainty, even when
    # confidence filtering retained just one of them. Preserve reliable color
    # and sugar constraints, but do not treat that incomplete grape subset as
    # a contradiction of known blends or another named variety.
    if len(raw['grape']) > 1 and query['grape'] and query['grape'] <= raw['grape']:
        flags['raw_multi_grape_uncertainty'] = True
        flags['suppressed_grape_query'] = sorted(query['grape'])
        query['grape'] = set()
        flags['query'] = {k: sorted(v) for k,v in query.items()}
    if any(len(v) > 1 for v in query.values()):
        return current, dict(flags, reason='contradictory_reliable_attributes')
    if not any(query.values()):
        return current, dict(flags, reason='no_reliable_attributes')
    compatible = [i for i in original if not contradicted(families.attributes.rows[i], query)]
    rejected = [i for i in original if i not in compatible]
    flags.update(compatible_candidates=compatible, rejected_candidates=rejected)
    if not compatible:
        return current, dict(flags, reason='all_original_top5_contradict')
    head = int(current[0])
    if head in rejected:
        winner = compatible[0]
        flags.update(text_override=True, selected_candidate=winner,
                     reason='best_original_compatible_after_contradiction')
    else:
        # Preserve an already-compatible visual decision. Reliable text is a
        # constraint; positive overlap is not a reason to discard unknown rows.
        winner = head
        flags.update(selected_candidate=winner, reason='current_head_compatible')
    # Keep the selected head, then original visual order among compatible rows,
    # and contradictions last within Top5. The remaining retrieval is untouched.
    top = [winner] + [i for i in compatible if i != winner] + rejected
    tail = [int(i) for i in current if int(i) not in original]
    result = np.asarray(top + tail)
    flags['text_filter_applied'] = bool(rejected)
    return result, flags
