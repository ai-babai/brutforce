"""Replace only previous metadata-missing GPU reader rows with verified additions."""
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
    p.add_argument('--full-inputs', type=Path, required=True)
    p.add_argument('--previous-inputs', type=Path, required=True)
    p.add_argument('--previous-reader', type=Path, required=True)
    p.add_argument('--additional-reader', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    full = read(a.full_inputs)
    previous = {r['case_id']: r for r in read(a.previous_inputs)}
    base_rows = read(a.previous_reader)
    base = {r['case_id']: r for r in base_rows}
    new_rows = read(a.additional_reader)
    new = {r['case_id']: r for r in new_rows}
    if len(full) != len(previous) or len(base) != len(base_rows) or len(new) != len(new_rows):
        raise ValueError('duplicate or missing reader inputs')
    missing = {r['case_id'] for r in previous.values() if r['target_metadata_state'] == 'missing'}
    if set(new) != missing or set(base) != set(previous):
        raise ValueError('new reader must contain exactly previous metadata-missing cases')
    output = []
    for row in full:
        case_id = row['case_id']
        item = new[case_id] if case_id in missing else base[case_id]
        if any(item.get(k) != row[k] for k in ('query_sha256', 'track', 'dataset')):
            raise ValueError('reader query/track mismatch')
        if item.get('crop_sha256') != row['crop_sha256']:
            raise ValueError('reader view SHA mismatch')
        if case_id not in missing and row['crop_sha256'] != previous[case_id]['crop_sha256']:
            raise ValueError('previous reader view altered')
        output.append(item)
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in output))
    print(json.dumps({'rows': len(output), 'replaced': len(missing),
                      'raw_sha256': sha(a.out), 'source_sha256': sha(Path(__file__))}))


if __name__ == '__main__':
    main()
