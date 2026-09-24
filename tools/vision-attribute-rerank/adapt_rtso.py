#!/usr/bin/env python3
"""Join saved RT-DETR+SO400M ranks to OCR from the identical RT-DETR crop."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index(path: Path) -> dict[str, dict]:
    result = {}
    for row in map(json.loads, path.read_text().splitlines()):
        cid = row['case_id']
        if cid in result:
            raise ValueError(f'duplicate case: {cid}')
        result[cid] = row
    return result


def adapt(rtso: dict, old: dict, old_file_sha256: str) -> dict:
    cid = rtso['case_id']
    if cid != old['case_id'] or rtso['track'] != old['track']:
        raise ValueError(f'case/track mismatch: {cid}')
    original = old.get('result') or {}
    if (rtso['query_sha256'] != old['query_sha256'] or
            original.get('image_sha256') != rtso['query_sha256']):
        raise ValueError(f'image SHA mismatch: {cid}')
    if rtso.get('selection') != original.get('selection'):
        raise ValueError(f'bottle selection mismatch: {cid}')
    if rtso.get('label_context_box') != original.get('label_context_box'):
        raise ValueError(f'label crop mismatch: {cid}')
    if 'ocr_text' in rtso:
        raise ValueError(f'OCR already present: {cid}')
    adapted = dict(rtso)
    adapted['ocr_text'] = original.get('ocr_text') or ''
    adapted['ocr_error'] = original.get('ocr_error')
    adapted['ocr_source'] = {'kind': 'saved same-crop RT-DETR HTTP response',
                             'source_file_sha256': old_file_sha256}
    return adapted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtso', type=Path, required=True)
    parser.add_argument('--old-rt', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    rtso, old = index(args.rtso), index(args.old_rt)
    if set(rtso) != set(old):
        raise ValueError('source case sets differ')
    old_sha = sha(args.old_rt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w') as handle:
        for cid, row in rtso.items():
            handle.write(json.dumps(adapt(row, old[cid], old_sha), ensure_ascii=False) + '\n')
    print(json.dumps({'rows': len(rtso), 'rtso_sha256': sha(args.rtso),
                      'old_rt_sha256': old_sha, 'out_sha256': sha(args.out)}))


if __name__ == '__main__':
    main()
