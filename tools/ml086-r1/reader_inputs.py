"""Export target-only reader inputs; never send Top20 or catalog to reader host."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, nargs='+', required=True)
    parser.add_argument('--crop-roots', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if len(args.inputs) != len(args.crop_roots):
        raise ValueError('one crop root per input')
    allowed = ('case_id', 'dataset', 'track', 'query_sha256', 'crop', 'crop_sha256')
    rows = []
    for path, root in zip(args.inputs, args.crop_roots):
        for line in path.read_text().splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row['crop']:
                crop = root / row['crop']
                if hashlib.sha256(crop.read_bytes()).hexdigest() != row['crop_sha256']:
                    raise ValueError(f'crop SHA mismatch {row["case_id"]}')
            rows.append(row)
    if len(rows) != len({row['case_id'] for row in rows}):
        raise ValueError('duplicate case ID')
    export = [{key: row[key] for key in allowed} for row in rows]
    args.out.write_text(''.join(json.dumps(row) + '\n' for row in export))
    print(json.dumps({'rows': len(export),
                      'cropped': sum(bool(row['crop']) for row in export),
                      'sha256': hashlib.sha256(args.out.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
