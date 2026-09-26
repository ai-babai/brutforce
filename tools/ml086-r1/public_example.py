"""Save a public-origin observation card without candidate data or gold."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matched', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    rows = (json.loads(line) for line in a.matched.read_text().splitlines() if line.strip())
    row = next((r for r in rows if r['observations'] and
                any(o['field_status'] == 'observed' for o in r['observations'])), None)
    if row is None:
        raise ValueError('no observed public label available')
    example = {key: row[key] for key in ('case_id', 'dataset', 'track', 'query_sha256',
                                         'target_box', 'crop_sha256', 'reader', 'reader_status')}
    example['provenance'] = 'public image -> ORT6 selected target -> derived JPEG -> candidate-blind reader'
    example['gold_or_private_label'] = 'not loaded'
    example['observations'] = row['observations']
    a.out.write_text(json.dumps(example, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'example_case_id': row['case_id'], 'observation_count': len(row['observations'])}))


if __name__ == '__main__':
    main()
