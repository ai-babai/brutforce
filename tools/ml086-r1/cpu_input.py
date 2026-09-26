"""Adapt runtime-owner same-view Paddle OCR, explicitly filling no-target neutrals."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--ocr', type=Path, nargs='+', required=True)
    p.add_argument('--slim', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    if len(a.ocr) != len(a.slim):
        raise ValueError('one input manifest per OCR batch')
    inputs = read(a.inputs)
    ocr_rows = []
    for ocr_path, slim_path in zip(a.ocr, a.slim):
        expected_sha = digest(slim_path)
        batch = read(ocr_path)
        if any(item.get('inputs_sha256') != expected_sha for item in batch):
            raise ValueError('OCR received different input manifest')
        ocr_rows.extend(batch)
    ocr = {r['case_id']: r for r in ocr_rows}
    if len(ocr) != len(ocr_rows) or set(ocr) != {r['case_id'] for r in inputs if r['crop']}:
        raise ValueError('OCR IDs must equal cropped input IDs')
    result = []
    for row in inputs:
        common = {k: row[k] for k in ('case_id', 'dataset', 'track', 'query_sha256', 'crop_sha256')}
        if row['crop']:
            item = ocr[row['case_id']]
            if any(item.get(k) != row[k] for k in common):
                raise ValueError('OCR mismatched query/crop ' + row['case_id'])
            texts = item.get('texts', [])
            scores = item.get('scores', [])
            polygons = item.get('polygons', [])
            if len(texts) != len(scores) or len(texts) != len(polygons):
                raise ValueError('OCR text, score, polygon mismatch')
            result.append({**common, 'status': 'error' if item.get('error') else 'ok',
                           'text': '\n'.join(texts), 'scores': scores, 'polygons': polygons,
                           'elapsed_ms': item.get('ocr_ms'), 'error': item.get('error')})
        else:
            state = 'metadata_missing' if row['target_metadata_state'] == 'missing' else 'no_target'
            result.append({**common, 'status': state, 'text': '', 'scores': [],
                           'polygons': [], 'elapsed_ms': 0, 'error': None})
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in result))
    print(json.dumps({'rows': len(result), 'no_target': sum(r['status'] == 'no_target' for r in result),
                      'errors': sum(r['status'] == 'error' for r in result),
                      'raw_sha256': digest(a.out), 'source_sha256': digest(Path(__file__))}))


if __name__ == '__main__':
    main()
