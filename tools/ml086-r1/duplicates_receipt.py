"""Seal public-only organizer duplicate-photo target provenance for trusted QA."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--b-sidecar', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    inputs = [r for r in read(a.inputs) if r['dataset'] == 'organizer']
    sidecar_rows = read(a.b_sidecar)
    sidecar = {r['case_id']: r for r in sidecar_rows}
    if len(inputs) != 103 or len(sidecar_rows) != 103 or len(sidecar) != 103:
        raise ValueError('full organizer public input and B independent capture required')
    groups = collections.defaultdict(list)
    for row in inputs:
        captured = sidecar[row['case_id']]
        branch = captured.get('branches_top20_whole') or captured.get('branches_top20', {}).get('whole', [])
        whole = [x['slug'] if isinstance(x, dict) else x for x in branch]
        if (row['target_metadata_state'] != 'confirmed_ort6' or
                captured['query_sha256'] != row['query_sha256'] or
                captured['target_box'] != row['target_box'] or
                whole != row['fixed_top20']):
            raise ValueError('B independent target capture not identical to ORT6 input')
        groups[row['query_sha256']].append(row)
    repeated = []
    for query_sha, rows in groups.items():
        if len(rows) < 2:
            continue
        boxes = {tuple(r['target_box']) if r['target_box'] else None for r in rows}
        crops = {r['crop_sha256'] for r in rows}
        pools = {tuple(r['fixed_top20']) for r in rows}
        if len(boxes) != 1 or len(crops) != 1 or len(pools) != 1:
            raise ValueError('same photo has divergent physical target, reader view, or pool')
        repeated.append({'public_query_sha256': query_sha,
                         'case_ids': [r['case_id'] for r in rows],
                         'target_status': 'confirmed_ort6' if rows[0]['target_box'] else 'confirmed_no_target',
                         'target_box': rows[0]['target_box'],
                         'reader_crop_sha256': rows[0]['crop_sha256'],
                         'top20_sha256': hashlib.sha256(json.dumps(rows[0]['fixed_top20'],
                                                            ensure_ascii=False,
                                                            separators=(',', ':')).encode()).hexdigest(),
                         'source': 'independent B ORT6 per-ID capture, strict whole Top20 and target box'})
    receipt = {'organizer_ids': len(inputs), 'unique_public_photo_sha': len(groups),
               'duplicate_groups': repeated, 'groups_count': len(repeated),
               'gold_loaded': False, 'source_inputs_sha256': sha(a.inputs),
               'source_b_sidecar_sha256': sha(a.b_sidecar), 'source_code_sha256': sha(Path(__file__))}
    a.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'groups_count': len(repeated), 'receipt_sha256': sha(a.out)}))


if __name__ == '__main__':
    main()
