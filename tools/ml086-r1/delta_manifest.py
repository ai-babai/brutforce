"""Export only newly recovered public target views with both JPEG/PNG hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous', type=Path, required=True)
    p.add_argument('--full', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    previous = {r['case_id']: r for r in read(a.previous)}
    full = read(a.full / 'inputs.jsonl')
    missing = {k for k, v in previous.items() if v['target_metadata_state'] == 'missing'}
    rows = []
    for row in full:
        if row['case_id'] not in missing:
            continue
        image = a.full / row['crop'] if row['crop'] else None
        if not image or sha(image) != row['crop_sha256']:
            raise ValueError('new JPEG missing or SHA mismatch')
        origin = a.full / 'origin-target-png' / (row['case_id'] + '.png')
        if sha(origin) != row['origin_target_png_sha256']:
            raise ValueError('origin PNG missing or SHA mismatch')
        rows.append({key: row[key] for key in ('case_id', 'dataset', 'track', 'query_sha256',
                                              'target_box', 'origin_target_png_sha256',
                                              'reader_view_transform', 'reader_view_size',
                                              'crop', 'crop_sha256')})
    if {r['case_id'] for r in rows} != missing:
        raise ValueError('delta IDs missing')
    a.out.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    print(json.dumps({'rows': len(rows), 'delta_manifest_sha256': sha(a.out),
                      'source_sha256': sha(Path(__file__))}))


if __name__ == '__main__':
    main()
