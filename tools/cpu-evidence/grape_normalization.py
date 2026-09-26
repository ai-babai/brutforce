"""Public-card-proven bilingual grape phrases; no SKU or evaluation labels."""
from __future__ import annotations

import re

from field_matcher import FieldMatcher
from matcher import contains, evidence_norm


# Each proposed pair occurs as an English phrase in cards.title with the
# corresponding SINGLE Russian cards.grapes. Reject the entire pair when any
# other single-grape card also has that phrase in its title.
CATALOG_PAIRS = (
    ('Каберне Совиньон', 'Cabernet Sauvignon'),
    ('Каберне Фран', 'Cabernet Franc'),
    ('Мерло', 'Merlot'),
    ('Пино Нуар', 'Pinot Noir'),
    ('Шардоне', 'Chardonnay'),
    ('Рислинг', 'Riesling'),
)


class CatalogGrapeNormalizer:
    def __init__(self, cards: dict):
        self.aliases: dict[str, str] = {}
        self.provenance: dict[str, dict] = {}
        for ru, en in CATALOG_PAIRS:
            canonical, alias = evidence_norm(ru), evidence_norm(en)
            fields = [evidence_norm(card.get('grapes') or '') for card in cards.values()
                      if isinstance(card.get('grapes'), str) and
                      not any(separator in card['grapes'] for separator in ',;/') and
                      contains(evidence_norm(card.get('title') or ''), alias)]
            support = sum(field == canonical for field in fields)
            conflict = sum(field != canonical for field in fields)
            self.provenance[alias] = {'canonical': canonical, 'supporting_cards': support,
                                      'conflicting_cards': conflict,
                                      'source': 'public cards.title + single cards.grapes'}
            if support and not conflict:
                self.aliases[alias] = canonical

    def canonicalize(self, value: str) -> str:
        text = evidence_norm(value)
        for alias, canonical in sorted(self.aliases.items(), key=lambda item: -len(item[0])):
            text = re.sub(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])',
                          canonical, text)
        return text


class GrapeNormalizedFieldMatcher(FieldMatcher):
    def __init__(self, cards: dict, catalog_slugs: list[str]):
        self.normalizer = CatalogGrapeNormalizer(cards)
        # Cross-language title/grape agreement is the same verified field, not
        # a new invented catalog value. All original cards remain unmodified.
        canonical_cards = {slug: {**card, 'title': self.normalizer.canonicalize(card.get('title') or '')}
                           for slug, card in cards.items()}
        super().__init__(canonical_cards, catalog_slugs)
        self.multiword_grapes = {value['grape'] for value in self.cards.values()
                                 if value['grape'] and len(value['grape'].split()) > 1}

    def ocr_lines(self, texts: list[str], scores: list[float]) -> list[tuple[str, float, str]]:
        lines = [(self.normalizer.canonicalize(text), float(score), text)
                 for text, score in zip(texts, scores)
                 if isinstance(text, str) and isinstance(score, (int, float)) and 0 <= score <= 1]
        # Never bridge a missing/malformed OCR line or nonadjacent lines.
        for i in range(len(texts)-1):
            left, right = texts[i:i+2]
            a, b = scores[i:i+2]
            if (not isinstance(left, str) or not isinstance(right, str) or
                    not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or
                    not 0 <= a <= 1 or not 0 <= b <= 1):
                continue
            joined = self.normalizer.canonicalize(left + ' ' + right)
            if any(contains(joined, grape) and
                   not contains(self.normalizer.canonicalize(left), grape) and
                   not contains(self.normalizer.canonicalize(right), grape)
                   for grape in self.multiword_grapes):
                lines.append((joined, min(float(a), float(b)), left + '\n' + right))
        return lines

    def observed_field(self, field, candidates, lines, threshold):
        # Adjacent-line stitching is solely for complete multiword grape phrases.
        if field != 'grape':
            lines = [line for line in lines if '\n' not in line[2]]
        return super().observed_field(field, candidates, lines, threshold)
