"""H2: categorical catalog-field evidence across the unchanged visual Top20."""
from __future__ import annotations

from matcher import GENERIC_PRODUCER, Matcher, contains, evidence_norm


class FieldMatcher(Matcher):
    def eligible_positions(self, ranks: list[dict]) -> list[int]:
        # No dependence on the visual winner's family, producer, or grape.
        candidates = [self.cards[item['slug']] for item in ranks]
        grapes = {card['grape'] for card in candidates if card['grape']}
        if len(grapes) < 2 or not any(card['producer'] or card['family'] for card in candidates):
            return []
        return list(range(len(ranks)))

    @staticmethod
    def observed_field(field: str, candidates: list[dict], lines: list[tuple[str, float, str]],
                       threshold: float) -> tuple[str | tuple[str, ...] | None, list[dict], bool]:
        phrases: dict[str | tuple[str, ...], set[str]] = {}
        for card in candidates:
            if field == 'grape':
                value = card['grape']
                tokens = {value} if value else set()
            elif field == 'line':
                # A family derived from a title lacking a verified grape may
                # include the variety itself; it is not a checked line field.
                value = card['family'] if card['grape'] else ()
                tokens = {token for token in value if len(token) >= 5}
            else:
                value = card['producer']
                tokens = {value} if value else set()
                tokens |= {word for word in value.split() if len(word) >= 6
                           and word not in GENERIC_PRODUCER} if value else set()
            if value and tokens:
                phrases.setdefault(value, set()).update(tokens)
        matched = [(value, {'field': field, 'value': value, 'literal': literal,
                             'score': score, 'source': 'selected_target_ocr'})
                   for value, tokens in phrases.items()
                   for text, score, literal in lines if score >= threshold
                   and any(contains(text, token) for token in tokens)]
        distinct = {value for value, _ in matched}
        return (next(iter(distinct)) if len(distinct) == 1 else None,
                [observation for _, observation in matched], len(distinct) > 1)

    def rerank(self, ranks: list[dict], positions: list[int], texts: list[str],
               scores: list[float]) -> tuple[list[dict], dict]:
        before = [item['slug'] for item in ranks]
        info = {'before': before, 'after': before.copy(), 'state': 'unknown',
                'field_positions_1based': [i + 1 for i in positions],
                'observations': [], 'ambiguous_fields': [],
                'ambiguous_observations': [], 'candidate_evidence': []}
        if len(texts) != len(scores):
            info['state'] = 'ocr_invalid_output'
            return ranks, info
        lines = [(evidence_norm(text), float(score), text) for text, score in zip(texts, scores)
                 if isinstance(text, str) and isinstance(score, (int, float)) and 0 <= score <= 1]
        cards = [self.cards[slug] for slug in before]
        observed = {}
        for field, threshold in (('producer', .75), ('line', .75), ('grape', .75)):
            value, literals, ambiguous = self.observed_field(field, cards, lines, threshold)
            if ambiguous:
                info['ambiguous_fields'].append(field)
                info['ambiguous_observations'].extend(literals)
            elif value:
                observed[field] = value
                info['observations'].extend(literals)
        for slug, card in zip(before, cards):
            evidence = {'slug': slug, 'fields': {}, 'identity': 'unknown'}
            for field, value in observed.items():
                if field == 'line':
                    catalog_value = card['family'] if card['grape'] else ()
                else:
                    catalog_value = card[field]
                evidence['fields'][field] = {
                    'catalog_value': catalog_value or None,
                    'catalog_source': {'producer': 'cards.winery', 'line': 'cards.title minus verified grape',
                                       'grape': 'cards.grapes confirmed by cards.title'}[field],
                    'state': 'unknown' if not catalog_value else
                             'matches' if catalog_value == value else 'contradicts'}
            states = [item['state'] for item in evidence['fields'].values()]
            if 'contradicts' in states:
                evidence['identity'] = 'contradicts'
            elif (observed.get('grape') and evidence['fields']['grape']['state'] == 'matches'
                  and any(evidence['fields'].get(anchor, {}).get('state') == 'matches'
                          for anchor in ('producer', 'line'))):
                evidence['identity'] = 'supported'
            info['candidate_evidence'].append(evidence)
        if not observed.get('grape') or not (observed.get('producer') or observed.get('line')):
            info['state'] = 'insufficient_field_evidence'
            return ranks, info
        if not info['candidate_evidence'] or info['candidate_evidence'][0]['identity'] != 'contradicts':
            info['state'] = 'visual_winner_not_contradicted'
            return ranks, info
        if not any(e['identity'] == 'supported' for e in info['candidate_evidence']):
            info['state'] = 'no_supported_identity'
            return ranks, info
        # Three categorical tiers, never arbitrary weights: independently
        # supported identity, unknown (original order), explicit contradiction.
        tiers = {'supported': 0, 'unknown': 1, 'contradicts': 2}
        result = [item for _, item in sorted(enumerate(ranks),
                  key=lambda pair: (tiers[info['candidate_evidence'][pair[0]]['identity']], pair[0]))]
        info['after'] = [item['slug'] for item in result]
        info['state'] = 'field_identity_promoted'
        return result, info
