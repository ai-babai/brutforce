"""Extend a sealed partial ORT6 reader view with verified missing metadata only."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageOps


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--partial-view', type=Path, required=True)
    p.add_argument('--missing-metadata', type=Path, required=True)
    p.add_argument('--image-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    old = read(a.partial_view / 'inputs.jsonl')
    metadata_rows = read(a.missing_metadata)
    metadata = {r['case_id']: r for r in metadata_rows}
    missing = {r['case_id'] for r in old if r['target_metadata_state'] == 'missing'}
    if len(metadata) != len(metadata_rows) or set(metadata) != missing:
        raise ValueError('missing-metadata IDs must equal previous missing IDs')
    a.out.mkdir()
    (a.out / 'crops').mkdir()
    (a.out / 'origin-target-png').mkdir()
    for source in (a.partial_view / 'crops').glob('*.jpg'):
        shutil.copy2(source, a.out / 'crops' / source.name)
    output = []
    additional = []
    for original in old:
        row = original.copy()
        if original['case_id'] in missing:
            meta = metadata[row['case_id']]
            if meta['query_sha256'] != row['query_sha256'] or meta.get('track', row['track']) != row['track']:
                raise ValueError('metadata query/track differs from fixed ORT6')
            result = meta.get('result') or meta
            whole = [x['slug'] for x in result.get('branches_top20', {}).get('whole', [])]
            box = result.get('target_box') or (result.get('evidence') or {}).get('target_box')
            if whole != row['fixed_top20'] or bool(box) != bool(whole):
                raise ValueError('metadata pool or target differs from fixed ORT6')
            row['target_metadata_state'] = 'confirmed_ort6'
            row['target_box'] = box
            if box:
                image_path = a.image_root / row['query_path']
                if digest(image_path) != row['query_sha256']:
                    raise ValueError('public image SHA mismatch')
                with Image.open(image_path) as raw:
                    image = ImageOps.exif_transpose(raw).convert('RGB')
                if len(box) != 4 or not (0 <= box[0] < box[2] <= image.width and
                                         0 <= box[1] < box[3] <= image.height):
                    raise ValueError('invalid physical target box')
                target = image.crop(box)
                origin = a.out / 'origin-target-png' / (row['case_id'] + '.png')
                target.save(origin)
                row['origin_target_png_sha256'] = digest(origin)
                scale = min(1, 768 / max(target.size))
                if scale < 1:
                    target = target.resize(tuple(max(1, round(n * scale)) for n in target.size),
                                           Image.Resampling.LANCZOS)
                row['reader_view_size'] = list(target.size)
                row['crop'] = 'crops/' + row['case_id'] + '.jpg'
                target.save(a.out / row['crop'], format='JPEG', quality=90, subsampling=0)
                row['crop_sha256'] = digest(a.out / row['crop'])
            additional.append({key: row[key] for key in
                               ('case_id', 'dataset', 'track', 'query_sha256', 'crop', 'crop_sha256')})
        elif row['crop'] and digest(a.out / row['crop']) != row['crop_sha256']:
            raise ValueError('previous reader JPEG changed')
        output.append(row)
    by_image = {}
    for row in output:
        if row['dataset'] != 'organizer':
            continue
        signature = (row['fixed_top20'], row['target_box'], row['crop_sha256'],
                     row['target_metadata_state'])
        previous = by_image.setdefault((row['track'], row['query_sha256']), signature)
        if signature != previous:
            raise ValueError('same public image has inconsistent target metadata or reader view')
    path = a.out / 'inputs.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in output))
    additional_path = a.out / 'additional-reader-slim.jsonl'
    additional_path.write_text(''.join(json.dumps(r) + '\n' for r in additional))
    (a.out / 'reader-slim.jsonl').write_text(''.join(json.dumps(
        {key: r[key] for key in ('case_id', 'dataset', 'track', 'query_sha256', 'crop', 'crop_sha256')})
        + '\n' for r in output))
    receipt = {'gold_loaded': False, 'rows': len(output), 'previous_metadata_missing': len(missing),
               'metadata_missing': sum(r['target_metadata_state'] == 'missing' for r in output),
               'new_crops': sum(bool(r['crop']) for r in additional),
               'previous_view_sha256': digest(a.partial_view / 'inputs.jsonl'),
               'new_metadata_sha256': digest(a.missing_metadata), 'full_input_sha256': digest(path),
               'full_reader_slim_sha256': digest(a.out / 'reader-slim.jsonl'),
               'additional_reader_slim_sha256': digest(additional_path),
               'source_sha256': digest(Path(__file__))}
    (a.out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
