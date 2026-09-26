"""Gold-blind, fixed-ORT6-Top20 evidence matcher on identical target crops."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path


# Generic spelling equivalences, independent of any SKU or query.
GRAPES = {
    'muscat': ('muscat', 'moscato', 'мускат'),
    'riesling': ('riesling', 'рислинг'),
    'syrah': ('syrah', 'shiraz', 'сира', 'шираз'),
    'cabernet_sauvignon': ('cabernet sauvignon', 'каберне совиньон'),
    'cabernet_franc': ('cabernet franc', 'каберне фран'),
    'chardonnay': ('chardonnay', 'шардоне'),
    'merlot': ('merlot', 'мерло'),
    'pinot_noir': ('pinot noir', 'пино нуар'),
    'saperavi': ('saperavi', 'саперави'),
    'malbec': ('malbec', 'мальбек'),
    'aligote': ('aligote', 'алиготе'),
    'viognier': ('viognier', 'вионье'),
    'rkatsiteli': ('rkatsiteli', 'ркацители'),
}
GENERIC = {'wine', 'винодельня', 'вино', 'estate', 'виноград', 'white',
           'red', 'beloe', 'krasnoe', 'brut', 'dry', 'сухое', 'красное', 'белое',
           'полусухое', 'полусладкое', 'сладкое', 'розовое', 'игристое',
           'тихое', 'белый', 'красный', 'розовый'}


def norm(text: str) -> str:
    text = unicodedata.normalize('NFKC', text or '').casefold().replace('ё', 'е')
    return re.sub(r'[^\w]+', ' ', text).strip()


def tokens(text: str) -> set[str]:
    return {word for word in norm(text).split() if len(word) >= 4 and word not in GENERIC}


def varieties(text: str) -> set[str]:
    value = ' ' + norm(text) + ' '
    return {key for key, variants in GRAPES.items()
            if any(' ' + norm(alias) + ' ' in value for alias in variants)}


def catalog_grapes(value: str) -> tuple[set[str], str]:
    chunks = re.split(r'[,;/]', value or '')
    if not value or any(not chunk.strip() for chunk in chunks):
        return set(), 'unknown'
    parsed = []
    for chunk in chunks:
        found = varieties(chunk)
        if len(found) != 1:
            return set(), 'unknown'
        parsed.extend(found)
    return set(parsed), 'provided'


def lines(text: str, crop_sha: str, source: str, scores=None, polygons=None) -> list[dict]:
    result = []
    literals = [x for x in text.splitlines() if x.strip() and x.strip().upper() != '<EMPTY>']
    for index, literal in enumerate(literals):
        if not literal.strip() or literal.strip().upper() == '<EMPTY>':
            continue
        hits = varieties(literal)
        confidence = scores[index] if scores and index < len(scores) else None
        polygon = polygons[index] if polygons and index < len(polygons) else None
        trustworthy = confidence is None or confidence >= 0.5
        result.append({'literal_text': literal, 'polygon': polygon,
                       'source_crop_sha256': crop_sha, 'reader': source,
                       'recognition_confidence': confidence,
                       'field': 'grape' if len(hits) == 1 and trustworthy else 'unclassified',
                       'field_value': next(iter(hits)) if len(hits) == 1 and trustworthy else None,
                       'field_status': 'observed' if len(hits) == 1 and trustworthy else 'unknown'})
    for index, (left, right) in enumerate(zip(literals, literals[1:])):
        # A printed variety can be split into two reader lines; joining adjacent
        # literal lines is evidence from this crop, not from any candidate.
        if len(norm(left).split()) != 1 or len(norm(right).split()) != 1:
            continue
        hits = varieties(left + ' ' + right)
        reliable = not scores or (index + 1 < len(scores) and
                                  scores[index] >= 0.5 and scores[index + 1] >= 0.5)
        if len(hits) == 1 and reliable and not varieties(left) and not varieties(right):
            result.append({'literal_text': left + ' ' + right, 'source_line_indices': [index, index + 1],
                           'polygon': None, 'source_crop_sha256': crop_sha, 'reader': source,
                           'recognition_confidence': None, 'field': 'grape',
                           'field_value': next(iter(hits)), 'field_status': 'observed'})
    return result


def rerank(rank: list[str], observations: list[dict], cards: dict[str, dict]) -> tuple[list[str], list[dict]]:
    text = '\n'.join(x['literal_text'] for x in observations
                     if x['recognition_confidence'] is None or x['recognition_confidence'] >= 0.5)
    words = tokens(text)
    seen_grapes = {x['field_value'] for x in observations if x['field_status'] == 'observed'}
    evidence = []
    for slug in rank:
        card = cards.get(slug, {})
        producer = tokens(card.get('winery', ''))
        # Catalog title may repeat the producer. It cannot identify a product
        # variant merely because the label shows its producer.
        title = tokens(card.get('title', '')) - producer
        matched_producer = sorted(producer & words)
        matched_title = sorted(title & words)
        grapes, grape_state = catalog_grapes(card.get('grapes', ''))
        positive = sorted(seen_grapes & grapes) if grape_state == 'provided' else []
        # A complete, *single* catalog variety confirmed also by title is the
        # only safe exclusion here. Missing labels/blends are never contradictory.
        title_grapes = varieties(card.get('title', ''))
        contradiction = bool(len(seen_grapes) == 1 and len(grapes) == 1 and
                             grapes == title_grapes and grapes.isdisjoint(seen_grapes))
        evidence.append({'slug': slug, 'producer_hits': matched_producer,
                         'title_hits': matched_title, 'grape_positive': positive,
                         'grape_field': {'value': sorted(grapes), 'source': 'organizer_card',
                                         'status': grape_state, 'verification':
                                         'title_and_card_consistent' if grapes == title_grapes and len(grapes) == 1 else 'unknown'},
                         'grape_relation': 'contradiction' if contradiction else
                                           'positive' if positive else 'unknown'})
    if not rank or not evidence[0]['producer_hits']:
        return rank[:], evidence
    first_producer = norm(cards.get(rank[0], {}).get('winery', ''))
    positions = [i for i, slug in enumerate(rank)
                 if norm(cards.get(slug, {}).get('winery', '')) == first_producer]
    # Only same-family members are permuted in their original Top20 slots.
    # A single shared winery token cannot certify a new target family.
    if len(positions) < 2:
        return rank[:], evidence
    def key(i):
        item = evidence[i]
        # Several literal title words beat a shared grape. Otherwise a generic
        # Riesling label can spuriously favor an unrelated same-winery SKU.
        return (item['grape_relation'] == 'contradiction',
                -min(len(item['title_hits']), 4), -len(item['grape_positive']), i)
    ordered = sorted(positions, key=key)
    if key(ordered[0])[:3] == key(positions[0])[:3] and all(
            key(i)[:3] == key(positions[0])[:3] for i in positions):
        return rank[:], evidence
    output = rank[:]
    for destination, source in zip(positions, ordered):
        output[destination] = rank[source]
    return output, evidence


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def unique(rows: list[dict]) -> dict[str, dict]:
    mapping = {r['case_id']: r for r in rows}
    if len(rows) != len(mapping):
        raise ValueError('duplicate case ID')
    return mapping


def run(inputs: list[dict], raw: dict[str, dict], cards: dict, source: str) -> list[dict]:
    if set(raw) != {r['case_id'] for r in inputs}:
        raise ValueError('reader must provide every input, including no-target rows')
    result = []
    for row in inputs:
        item = raw[row['case_id']]
        if any(item.get(k) != row[k] for k in ('query_sha256', 'track', 'dataset')):
            raise ValueError(f'reader query mismatch {row["case_id"]}')
        if row['crop'] and item.get('crop_sha256') != row['crop_sha256']:
            raise ValueError(f'reader crop mismatch {row["case_id"]}')
        status = item['status']
        if row['target_metadata_state'] == 'missing':
            if row['crop'] is not None or status not in ('no_target', 'metadata_missing'):
                raise ValueError('unverified target metadata must not be OCR-classified')
            status = 'metadata_missing'
        if status == 'ok' and row['crop']:
            text = item.get('text', '')
            obs = lines(text, row['crop_sha256'], source, item.get('scores'), item.get('polygons'))
        else:
            obs = []
        started = time.perf_counter_ns()
        ranking, evidence = rerank(row['fixed_top20'], obs, cards) if obs else (row['fixed_top20'][:], [])
        matcher_ms = (time.perf_counter_ns() - started) / 1e6
        if sorted(ranking) != sorted(row['fixed_top20']):
            raise ValueError('pool changed')
        prediction = {'ranked_slugs': ranking} if row['track'] == 'retrieval' else (
            {'slug': ranking[0]} if ranking else row['baseline_prediction'])
        result.append({'case_id': row['case_id'], 'dataset': row['dataset'], 'track': row['track'],
                       'query_sha256': row['query_sha256'], 'target_box': row['target_box'],
                       'crop_sha256': row['crop_sha256'], 'reader': source,
                       'reader_status': status, 'reader_elapsed_ms': item.get('elapsed_ms'),
                       'evaluation_status': 'not_run' if status == 'metadata_missing' else 'eligible',
                       'matcher_elapsed_ms': matcher_ms, 'observations': obs,
                       'candidate_evidence': evidence, 'before': row['fixed_top20'],
                       'after': ranking, 'result': {**prediction, 'ranked_slugs': ranking},
                       'http_status': row['baseline_http_status'],
                       'baseline_elapsed_ms': row['baseline_elapsed_ms'],
                       'timing_scope': 'cached_reader_plus_matcher; not HTTP'})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, nargs='+', required=True)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--cards', type=Path, required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    inputs = [r for path in a.inputs for r in read(path)]
    cards = json.loads(a.cards.read_text())
    output = run(inputs, unique(read(a.reader)), cards, a.name)
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in output))
    print(json.dumps({'rows': len(output), 'changed': sum(r['before'] != r['after'] for r in output),
                      'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(),
                      'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
