"""Join immutable five-card and twenty-card records after inference."""
import argparse
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args()
    five = rows(a.root / 'raw-five.jsonl')
    twenty = rows(a.root / 'raw-twenty.jsonl')
    if len(five) != 316 or len(twenty) != 316:
        raise ValueError(f'Full basket needed: five={len(five)} twenty={len(twenty)}')
    by_id = {r['case_id']: r for r in twenty}
    if len(by_id) != 316 or len({r['case_id'] for r in five}) != 316:
        raise ValueError('Duplicate case ID')
    with (a.root / 'raw-predictions.jsonl').open('w', encoding='utf-8') as stream:
        for row in five:
            later = by_id[row['case_id']]
            for key in ('query_sha256', 'b_ranked', 'b_action', 'missing_references'):
                if later[key] != row[key]:
                    raise ValueError(f'Mismatch {row["case_id"]} {key}')
            row.update({key: value for key, value in later.items() if key in
                ('groups20', 'final20', 'final20_reused', 'roman20_ranked')})
            row['roman_elapsed_ms'] += later['roman_elapsed_ms']
            if later['status'] == 'inference_error' and 'roman20_ranked' not in row:
                row['roman20_error'] = later['error']
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
