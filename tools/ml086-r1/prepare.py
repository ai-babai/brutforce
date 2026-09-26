"""Seal public ORT6 Top20 and the same route's selected target crops (no gold)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def unique(rows: list[dict]) -> dict[str, dict]:
    result = {row['case_id']: row for row in rows}
    if len(result) != len(rows):
        raise ValueError('duplicate case ID')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--ort6', type=Path, required=True)
    parser.add_argument('--target-metadata', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--dataset', choices=['eval', 'organizer'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if (args.out / 'receipt.json').exists():
        raise FileExistsError(args.out / 'receipt.json')
    public = json.loads(args.public.read_text())
    cases = unique(public['cases'])
    base = unique(jsonl(args.ort6))
    metadata = unique(jsonl(args.target_metadata))
    if not set(metadata) <= set(base) or set(base) != set(cases):
        raise ValueError('public/ORT6/metadata case IDs disagree')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'crops').mkdir(exist_ok=True)
    results = []
    for case_id, case in cases.items():
        row = base[case_id]
        query_sha = case.get('image_sha256', case.get('sha256'))
        image_path = case.get('image_path', case.get('path'))
        if row['query_sha256'] != query_sha or row['track'] != case.get('track', case.get('tracks', [None])[0]):
            raise ValueError(f'baseline mismatch {case_id}')
        src = args.image_root / image_path
        if digest(src) != query_sha:
            raise ValueError(f'public query image SHA mismatch {case_id}')
        pred = row.get('result') or {}
        rank = pred.get('ranked_slugs') or []
        if len(rank) > 20 or len(set(rank)) != len(rank):
            raise ValueError(f'bad ORT6 Top20 {case_id}')
        meta = metadata.get(case_id)
        box = None
        if meta:
            observed = meta.get('result') or {}
            evidence = observed.get('evidence') or {}
            box = evidence.get('target_box')
            whole = [x['slug'] for x in observed.get('branches_top20', {}).get('whole', [])]
            if meta['query_sha256'] != query_sha or meta['track'] != row['track'] or whole != rank:
                raise ValueError(f'metadata not identical to ORT6 pool {case_id}')
            if bool(box) != bool(rank):
                raise ValueError(f'target/rank mismatch {case_id}')
        crop_name = None
        crop_sha = None
        if box:
            with Image.open(src) as raw:
                image = ImageOps.exif_transpose(raw).convert('RGB')
            if len(box) != 4 or not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                raise ValueError(f'invalid physical target box {case_id}')
            crop_name = f'crops/{case_id}.png'
            image.crop(box).save(args.out / crop_name)
            crop_sha = digest(args.out / crop_name)
        results.append({'case_id': case_id, 'dataset': args.dataset, 'track': row['track'],
                        'query_sha256': query_sha, 'query_path': image_path,
                        'target_box': box, 'crop': crop_name, 'crop_sha256': crop_sha,
                        'target_metadata_state': 'confirmed_ort6' if meta else 'missing',
                        'baseline_http_status': row['http_status'],
                        'baseline_elapsed_ms': row['elapsed_ms'],
                        'baseline_prediction': {key: pred[key] for key in ('slug', 'action') if key in pred},
                        'fixed_top20': rank})
    output = args.out / 'inputs.jsonl'
    output.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results))
    receipt = {'dataset': args.dataset, 'gold_loaded': False, 'rows': len(results),
               'metadata_rows': len(metadata), 'cropped': sum(bool(x['crop']) for x in results),
               'sources_sha256': {name: digest(path) for name, path in
                                  [('public', args.public), ('ort6', args.ort6),
                                   ('target_metadata', args.target_metadata),
                                   ('source', Path(__file__))]},
               'input_sha256': digest(output)}
    (args.out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
