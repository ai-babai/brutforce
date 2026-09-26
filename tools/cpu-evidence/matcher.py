"""Gold-blind, same-family identity evidence on an unchanged visual Top20."""
from __future__ import annotations

import re

from ranking import norm


LOOKALIKE = str.maketrans({'A':'А','B':'В','C':'С','E':'Е','H':'Н','K':'К','M':'М',
                           'O':'О','P':'Р','T':'Т','X':'Х','Y':'У','a':'а','c':'с',
                           'e':'е','o':'о','p':'р','x':'х','y':'у'})
GENERIC = {'wine', 'vino', 'vin', 'krasnoe', 'beloe', 'rozovoe',
           'suhoe', 'polusuhoe', 'sladkoe', 'polusladkoe', 'brut', 'reserve',
           'rezerv', 'seriya', 'series', 'lineika', 'line', 'kollekciya',
           'collection'}
GENERIC_PRODUCER = {'winery', 'estate', 'shato', 'chateau', 'vinodelnya'}


def contains(text: str, phrase: str) -> bool:
    return bool(phrase and re.search(r'(?<![a-z0-9])' + re.escape(phrase) +
                                     r'(?![a-z0-9])', text))


def evidence_norm(value: str) -> str:
    # Same tested mixed-script correction as night-experiments/homoglyph_ablation.py.
    # Pure Latin words and digits are not rewritten.
    def correct(match):
        token = match.group()
        return token.translate(LOOKALIKE) if re.search('[А-Яа-яЁё]', token) and re.search('[A-Za-z]', token) else token
    return norm(re.sub(r'[A-Za-zА-Яа-яЁё0-9]+', correct, value))


def card_identity(card: dict) -> dict:
    """Trust a single catalog grape only when the title independently names it."""
    title = evidence_norm(card.get('title') or '')
    producer = evidence_norm(card.get('winery') or '')
    raw_grapes = card.get('grapes') or ''
    grapes = [evidence_norm(value) for value in re.split(r'[,;/]', raw_grapes)] if isinstance(raw_grapes, str) else []
    grape = grapes[0] if len(grapes) == 1 and len(grapes[0]) >= 5 and contains(title, grapes[0]) else None
    remainder = re.sub(r'(?<![a-z0-9])' + re.escape(grape) + r'(?![a-z0-9])', ' ', title) if grape else title
    producer_words = set(producer.split())
    family = tuple(word for word in remainder.split()
                   if len(word) >= 4 and word not in producer_words and word not in GENERIC
                   and not word.isdigit())
    return {'producer': producer, 'family': family, 'grape': grape,
            'catalog_source': 'cards: winery/title/grapes; grape confirmed by title'}


class Matcher:
    def __init__(self, cards: dict, catalog_slugs: list[str]):
        if set(cards) != set(catalog_slugs):
            raise ValueError('evidence cards must cover exactly the pinned catalog slugs')
        self.cards = {slug: card_identity(cards[slug]) for slug in catalog_slugs}

    def family_positions(self, ranks: list[dict]) -> list[int]:
        if not ranks:
            return []
        first = self.cards[ranks[0]['slug']]
        if not first['producer'] or not first['grape'] or not self.anchor_tokens(first):
            return []
        positions = [i for i, item in enumerate(ranks) if
                     self.cards[item['slug']]['producer'] == first['producer'] and
                     self.cards[item['slug']]['family'] == first['family'] and
                     self.cards[item['slug']]['grape']]
        # Only an actionable variant near the visual winner warrants the OCR cost.
        if not any(i < 5 and self.cards[ranks[i]['slug']]['grape'] != first['grape']
                   for i in positions):
            return []
        return positions

    @staticmethod
    def anchor_tokens(card: dict) -> tuple[str, ...]:
        # A grape-only title has no series name: a visible producer is its anchor.
        source = card['family'] if card['family'] else card['producer'].split()
        return tuple(token for token in source if len(token) >= 5 and
                     token not in GENERIC_PRODUCER)

    def rerank(self, ranks: list[dict], positions: list[int], texts: list[str],
               scores: list[float]) -> tuple[list[dict], dict]:
        before = [item['slug'] for item in ranks]
        info = {'before': before, 'after': before.copy(), 'state': 'unknown',
                'family_positions_1based': [i + 1 for i in positions],
                'observations': [], 'candidate_evidence': []}
        if len(texts) != len(scores):
            info['state'] = 'ocr_invalid_output'
            return ranks, info
        family = self.cards[before[0]]['family']
        anchor_tokens = self.anchor_tokens(self.cards[before[0]])
        # Individual OCR lines preserve recognition confidence; never synthesize missing text.
        lines = [(evidence_norm(text), float(score), text) for text, score in zip(texts, scores)
                 if isinstance(text, str) and isinstance(score, (float, int)) and 0 <= score <= 1]
        anchors = [{'literal': texts[i], 'score': score} for i, score in enumerate(scores)
                   if isinstance(score, (float, int)) and score >= .65 and
                   isinstance(texts[i], str) and
                   any(contains(evidence_norm(texts[i]), token) for token in anchor_tokens)]
        if not anchors:
            info['state'] = 'family_not_observed' if family else 'producer_not_observed'
            return ranks, info
        variants = {self.cards[before[i]]['grape'] for i in positions}
        observed = {grape for grape in variants if any(score >= .75 and contains(text, grape)
                                                      for text, score, _ in lines)}
        info['observations'] = [{'field': 'family' if family else 'producer',
                                 'literal': anchor['literal'],
                                 'score': anchor['score']} for anchor in anchors]
        info['observations'] += [{'field': 'grape', 'value': grape,
                                  'source': 'target_ocr_line', 'literal': literal,
                                  'score': score}
                                 for grape in sorted(observed)
                                 for text, score, literal in lines
                                 if score >= .75 and contains(text, grape)]
        if len(observed) != 1:
            info['state'] = 'grape_ambiguous' if observed else 'grape_not_observed'
            return ranks, info
        grape = next(iter(observed))
        for i in positions:
            candidate = self.cards[before[i]]
            info['candidate_evidence'].append({'slug': before[i], 'field': 'grape',
                'catalog_value': candidate['grape'], 'catalog_source': candidate['catalog_source'],
                'state': 'observed' if candidate['grape'] == grape else 'contradicts'})
        if self.cards[before[0]]['grape'] == grape:
            info['state'] = 'visual_winner_supported'
            return ranks, info
        # Keep the exact visual pool and all non-family slots stable. No score fusion.
        ordered = sorted(positions, key=lambda i: self.cards[before[i]]['grape'] != grape)
        result = ranks.copy()
        for dst, src in zip(positions, ordered):
            result[dst] = ranks[src]
        info['after'] = [item['slug'] for item in result]
        info['state'] = 'same_family_variant_promoted'
        return result, info
