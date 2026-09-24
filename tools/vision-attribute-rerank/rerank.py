#!/usr/bin/env python3
"""Offline, gold-blind attribute rerank of saved Top-20 lists (RULES-v1.md)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path


COLORS = {'белое', 'красное', 'розовое'}
SWEET = {'сухое', 'полусухое', 'полусладкое', 'сладкое', 'брют', 'экстра брют'}
GENERIC = {'вино', 'винодельня', 'семейная', 'белое', 'красное', 'розовое',
           'сухое', 'полусухое', 'полусладкое', 'сладкое', 'брют', 'игристое',
           'русское', 'российское', 'шампанское', 'винный', 'estate', 'wine'}
WORD = re.compile(r'(?<![\w])([а-яёa-z]+)(?![\w])', re.I)
YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value: str) -> str:
    value = unicodedata.normalize('NFKC', value or '').casefold().replace('ё', 'е')
    return re.sub(r'[^а-яa-z0-9]+', ' ', value).strip()


def words(value: str) -> set[str]:
    return set(WORD.findall(norm(value)))


def unique(values: set[str]) -> str | None:
    return next(iter(values)) if len(values) == 1 else None


def parse_ocr(value: str) -> dict[str, str | None]:
    text = norm(value)
    color = unique({x for x in COLORS if re.search(r'(?<!\w)' + x + r'(?!\w)', text)})
    sweet_values = {x for x in SWEET if re.search(r'(?<!\w)' + x + r'(?!\w)', text)}
    if 'экстра брют' in sweet_values:
        sweet_values.discard('брют')
    sweet = unique(sweet_values)
    years = set(YEAR.findall(text))
    return {'color': color, 'sweetness': sweet, 'year': unique(years)}


def catalog(display_path: Path, csv_path: Path) -> dict[str, dict]:
    official = defaultdict(list)
    with csv_path.open(newline='') as handle:
        for row in csv.DictReader(handle):
            official[row['Slug']].append(row)
    result = {}
    display = {row['slug']: row for row in map(json.loads, display_path.read_text().splitlines())}
    for slug in set(display) | set(official):
        item = display.get(slug, {})
        csv_rows = official.get(slug, [])
        display_color = unique(COLORS & words(item.get('category_and_sweetness', '')))
        csv_color = unique({norm(row['Категория']) for row in csv_rows}) if csv_rows else None
        if csv_color not in COLORS:
            csv_color = None
        color = display_color if display_color and display_color == csv_color else (csv_color if not item and csv_color else None)
        display_sweet = norm(item.get('sweetness', ''))
        category_sweet = parse_ocr(item.get('category_and_sweetness', ''))['sweetness']
        sweetness = display_sweet if display_sweet in SWEET and display_sweet == category_sweet else None
        title = item.get('title') or (csv_rows[0]['Название вина'] if csv_rows else '')
        display_year = unique(set(YEAR.findall(item.get('title', ''))))
        csv_year = unique(set().union(*(set(YEAR.findall(row['Название вина'])) for row in csv_rows))) if csv_rows else None
        year = display_year if display_year and display_year == csv_year else None
        producer = item.get('producer') or (csv_rows[0]['Винодельня'] if csv_rows else '')
        producer_key = item.get('producer_slug') or norm(producer)
        title_key = re.sub(r'(?<!\d)(?:19|20)\d{2}(?!\d)', '', norm(title)).strip()
        result[slug] = {'producer': producer, 'producer_key': producer_key,
                        'title': title, 'title_key': title_key,
                        'color': color, 'sweetness': sweetness, 'year': year,
                        'catalog_conflict': bool(item and csv_rows and not color and display_color and csv_color and display_color != csv_color)}
    return result


def get_payload(record: dict) -> tuple[dict, list[dict], str, str]:
    payload = record.get('result') or record
    if 'ranked' in payload:
        ranked = payload['ranked'] or []
    else:
        ranked = (payload.get('variants_top20') or {}).get('all') or []
    ocr = payload.get('ocr') or {}
    ocr_text = ocr.get('raw_text', '') if isinstance(ocr, dict) else payload.get('ocr_text', '')
    ocr_action = ocr.get('action', '') if isinstance(ocr, dict) else ''
    if not ocr_text:
        ocr_text = payload.get('ocr_text') or ''
    return payload, ranked, ocr_text, ocr_action


def evidence_ok(ocr_text: str, item: dict) -> bool:
    seen = words(ocr_text)
    title = {w for w in words(item['title']) if len(w) >= 5 and w not in GENERIC}
    producer = {w for w in words(item['producer']) if len(w) >= 5 and w not in GENERIC}
    title_hits = len(title & seen)
    return title_hits >= 2 or (title_hits >= 1 and bool(producer & seen))


def rerank(record: dict, metadata: dict[str, dict]) -> dict:
    payload, ranked, ocr_text, ocr_action = get_payload(record)
    before = [x['slug'] for x in ranked]
    info = {'case_id': record['case_id'], 'track': record['track'], 'before': before,
            'after': before.copy(), 'attributes': {'color': None, 'sweetness': None, 'year': None},
            'groups': [], 'changed': False, 'reason': 'no_safe_change'}
    status = record.get('status', 'ok')
    prediction = payload.get('prediction') or payload.get('predictions', {}).get('all') or payload
    action = prediction.get('action') if isinstance(prediction, dict) else None
    prediction_slug = prediction.get('slug') if isinstance(prediction, dict) else None
    info['before_prediction_slug'] = prediction_slug
    info['after_prediction_slug'] = prediction_slug
    if status != 'ok' or action in ('no_match', 'insufficient_information', 'unknown') or ocr_action not in ('', 'wine') or not ranked:
        info['reason'] = 'status_or_action_or_ocr_gate'
        return info
    attributes = parse_ocr(ocr_text)
    info['attributes'] = attributes
    if not any(attributes.values()):
        info['reason'] = 'no_unambiguous_attribute'
        return info
    groups = defaultdict(list)
    for index, slug in enumerate(before):
        item = metadata.get(slug)
        if item and item['title_key'] and item['producer_key']:
            groups[(item['producer_key'], item['title_key'])].append(index)
    after = before.copy()
    for positions in groups.values():
        if len(positions) < 2:
            continue
        reference = metadata[before[positions[0]]]
        if not evidence_ok(ocr_text, reference):
            continue
        scores = {}
        for pos in positions:
            item = metadata[before[pos]]
            scores[before[pos]] = sum(1 if item[field] == value else -1 for field, value in attributes.items()
                                            if value and item[field])
        if len(set(scores.values())) < 2:
            continue
        ordered = sorted(positions, key=lambda pos: (-scores[before[pos]], pos))
        for position, source_position in zip(positions, ordered):
            after[position] = before[source_position]
        info['groups'].append({'positions_1based': [x + 1 for x in positions],
                               'scores': scores, 'order_after': [after[x] for x in positions]})
    info['after'] = after
    info['changed'] = after != before
    info['reason'] = 'same_producer_title_attribute_rerank' if info['changed'] else 'no_safe_change'
    if record['track'] == 'service' and before and before[0] == prediction_slug and after[0] != before[0]:
        info['after_prediction_slug'] = after[0]
    return info


def run(input_path: Path, output_path: Path, metadata: dict[str, dict], rule_sha: str) -> dict:
    if output_path.exists():
        raise FileExistsError(output_path)
    rows = [json.loads(line) for line in input_path.read_text().splitlines()]
    start = time.perf_counter_ns()
    results = [rerank(row, metadata) for row in rows]
    elapsed_ns = time.perf_counter_ns() - start
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w') as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    return {'input': str(input_path), 'input_sha256': sha(input_path),
            'output': str(output_path), 'output_sha256': sha(output_path),
            'rules_sha256': rule_sha, 'rows': len(rows),
            'changed_rank_lists': sum(row['changed'] for row in results),
            'cpu_reorder_total_ms': elapsed_ns / 1_000_000,
            'cpu_reorder_mean_ms': elapsed_ns / len(rows) / 1_000_000 if rows else 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display', type=Path, required=True)
    parser.add_argument('--official-csv', type=Path, required=True)
    parser.add_argument('--input', action='append', required=True, help='name=path')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    metadata = catalog(args.display, args.official_csv)
    rule_sha = sha(Path(__file__).with_name('RULES-v1.md'))
    summaries = []
    for entry in args.input:
        name, value = entry.split('=', 1)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            raise ValueError('bad input name')
        summaries.append(run(Path(value), args.out_dir / f'{name}.jsonl', metadata, rule_sha) | {'name': name})
    manifest = {'schema_version': 1, 'kind': 'gold-blind post-hoc development rerank',
                'display_sha256': sha(args.display), 'official_csv_sha256': sha(args.official_csv),
                'rules_sha256': rule_sha, 'runs': summaries}
    (args.out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(summaries), 'rows': sum(x['rows'] for x in summaries),
                      'changed_rank_lists': sum(x['changed_rank_lists'] for x in summaries)}))


if __name__ == '__main__':
    main()
