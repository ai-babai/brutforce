"""Offline encoder swap on saved full-HTTP detector selections and OCR ranks.

Reconstruct crops from original SHA-checked bytes. The detector and OCR are
not run again; only whole/label embeddings change. This is not live serving.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from detector_run import cases_from_manifest, image_path
from fuse import VARIANTS, rank_fuse
from model import load_image
from ranking import top
from so400m_ablation import Embedder, MODELS


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=MODELS, required=True)
    p.add_argument('--detector', required=True)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--index-dir', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--image-root', type=Path, required=True)
    p.add_argument('--http-rows', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--device', default='cuda')
    args = p.parse_args()

    manifest_sha, cases_raw = cases_from_manifest(args.manifest)
    cases = {x['case_id']: x for x in cases_raw}
    if len(cases) != len(cases_raw):
        raise ValueError('duplicate manifest case ID')
    http_raw = args.http_rows.read_bytes()
    rows = [json.loads(x) for x in http_raw.splitlines() if x.strip()]
    by_id = {x['case_id']: x for x in rows}
    if len(by_id) != len(rows) or set(by_id) != set(cases):
        raise ValueError('HTTP/manifest case IDs mismatch')

    index_info = json.loads((args.index_dir/'index-info.json').read_text())
    expected_model = '@'.join(MODELS[args.model])
    indexed_model = index_info.get('model')
    if indexed_model is None and index_info.get('full_encoder') == index_info.get('label_encoder'):
        indexed_model = index_info.get('full_encoder')
    if indexed_model != expected_model:
        raise ValueError('index/query encoder mismatch')
    catalog_raw = args.catalog.read_bytes()
    if index_info['catalog_manifest_sha256'] != hashlib.sha256(catalog_raw).hexdigest():
        raise ValueError('index/catalog hash mismatch')
    catalog_slugs = [x['slug'] for x in json.loads(catalog_raw)['references']]
    index = np.load(args.index_dir/'index.npz')
    full, label, slugs = index['full'], index['label'], list(index['slugs'])
    if slugs != catalog_slugs:
        raise ValueError('index/catalog slug order mismatch')
    full_valid = np.isfinite(full).all(axis=1)
    label_valid = np.isfinite(label).all(axis=1)

    embedder = Embedder(args.device, args.model)
    output = []
    for n, case in enumerate(cases_raw, 1):
        cid = case['case_id']; saved = by_id[cid]
        if (saved['variant'] != args.detector or saved['http_status'] != 200
                or saved['query_sha256'] != case['sha256']
                or saved['track'] != case['track']
                or saved['result']['image_sha256'] != case['sha256']):
            raise ValueError('HTTP identity/status mismatch '+cid)
        result = saved['result']
        selected = result['selection']['selected_box']
        whole_rank, label_rank = [], []
        whole_ms = label_ms = 0
        if selected is not None:
            image = load_image(image_path(args.image_root, case), case['sha256'])
            target = image if case['track'] == 'retrieval' else image.crop(selected)
            region = result['label_context_box']
            if region is None:
                raise ValueError('selected target lacks label context '+cid)
            t = time.perf_counter(); vf = embedder.features([target])[0]
            whole_ms = round((time.perf_counter()-t)*1000)
            t = time.perf_counter(); vl = embedder.features([target.crop(region)])[0]
            label_ms = round((time.perf_counter()-t)*1000)
            whole_rank = top(np.where(full_valid, full@vf, np.nan), slugs)
            label_rank = top(np.where(label_valid, label@vl, np.nan), slugs)
        branches = {'whole': whole_rank, 'label': label_rank,
                    'ocr': result['branches_top20']['ocr']}
        variants = {name: rank_fuse({key: branches[key] for key in subset})
                    for name, subset in VARIANTS.items()}
        predictions = {
            name: ({'action': 'no_match'} if case['track'] == 'service' and selected is None
                   else {'slug': rank[0]['slug']} if rank
                   else {'action': 'insufficient_information'})
            for name, rank in variants.items()
        }
        output.append({
            'case_id': cid, 'track': case['track'], 'status': 'ok',
            'query_sha256': case['sha256'], 'manifest_sha256': manifest_sha,
            'detector': args.detector, 'encoder': expected_model,
            'selection': result['selection'], 'label_context_box': result['label_context_box'],
            'branches': branches, 'variants_top20': variants, 'predictions': predictions,
            'whole_embedding_ms': whole_ms, 'label_embedding_ms': label_ms,
            'source_http_elapsed_ms': saved['elapsed_ms'],
            'latency_kind': 'offline_embedding_only; not a new full HTTP request',
        })
        if n % 25 == 0:
            print(json.dumps({'queries': n, 'total': len(cases)}), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in output))
    lineage = {
        'detector': args.detector, 'encoder': expected_model,
        'index_sha256': hashlib.sha256((args.index_dir/'index.npz').read_bytes()).hexdigest(),
        'catalog_manifest_sha256': hashlib.sha256(catalog_raw).hexdigest(),
        'query_manifest_sha256': manifest_sha,
        'source_http_sha256': hashlib.sha256(http_raw).hexdigest(),
        'cases': len(output), 'no_new_detector_or_ocr_pass': True,
        'not_full_http_latency': True,
    }
    args.out.with_name(args.out.stem+'-lineage.json').write_text(json.dumps(lineage, indent=2)+'\n')
    print(json.dumps(lineage), flush=True)


if __name__ == '__main__':
    main()
