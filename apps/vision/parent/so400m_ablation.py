"""Controlled SigLIP2 SO400M/384 comparison on frozen OWLv2 v2 crops.

Only the shared visual encoder and its whole/label index change. The existing
OWLv2 target/crop choices, OCR ranks, catalog slug order and RRF stay fixed.
Excluded reference images remain unavailable, not replaced or relabeled.
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
from index import find_image
from model import load_image
from model import SIGLIP_ID, SIGLIP_REV
from ranking import top

MODEL_ID = 'google/siglip2-so400m-patch16-384'
MODEL_REV = 'dd658faac399427308559e2c3ac1e99cbe43845d'
VERSION_SUFFIX = '-owlv2-v2-crops-reference-gated-20260925'
MODELS = {'so400m384': (MODEL_ID, MODEL_REV), 'base224': (SIGLIP_ID, SIGLIP_REV)}


def read_rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


class Embedder:
    def __init__(self, device, model_key):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.device = device if device != 'cuda' or torch.cuda.is_available() else 'cpu'
        self.model_id, self.model_rev = MODELS[model_key]
        self.processor = AutoProcessor.from_pretrained(self.model_id, revision=self.model_rev)
        self.model = AutoModel.from_pretrained(
            self.model_id, revision=self.model_rev, use_safetensors=True
        ).to(self.device).eval()

    def features(self, images, batch_size=16):
        import torch.nn.functional as F
        outputs = []
        for offset in range(0, len(images), batch_size):
            inp = self.processor(images=images[offset:offset+batch_size], return_tensors='pt').to(self.device)
            with self.torch.inference_mode():
                value = self.model.get_image_features(**inp)
                if not isinstance(value, self.torch.Tensor):
                    value = value.pooler_output
                outputs.append(F.normalize(value.float(), dim=-1).cpu())
        if self.device.startswith('cuda'):
            self.torch.cuda.synchronize()
        return self.torch.cat(outputs).numpy()


def make_index(args):
    raw = args.catalog.read_bytes()
    refs = json.loads(raw)['references']
    slugs = [x['slug'] for x in refs]
    base_info = json.loads((args.v2_index/'index-info.json').read_text())
    base = np.load(args.v2_index/'index.npz')
    if (base_info['catalog_manifest_sha256'] != hashlib.sha256(raw).hexdigest()
            or list(base['slugs']) != slugs):
        raise ValueError('catalog/base index mismatch')
    region_rows = read_rows(args.regions)
    regions = {x['slug']: x for x in region_rows}
    if len(regions) != len(region_rows) or not set(regions).issubset(slugs):
        raise ValueError('duplicate or unknown reference region slug')
    decisions_raw = args.decisions.read_bytes()
    excluded = {x['slug']: x for x in json.loads(decisions_raw)['excluded']}
    if len(excluded) not in (19, 20):
        raise ValueError('expected versioned 19- or 20-reference gate')
    for ref in refs:
        if ref['slug'] in excluded and excluded[ref['slug']]['sha256'] != ref.get('sha256'):
            raise ValueError('reference gate image hash mismatch '+ref['slug'])
    model = Embedder(args.device, args.model)
    full = label = None
    pending_full, pending_label, positions = [], [], []
    indexed = 0
    started = time.perf_counter()

    def flush():
        nonlocal full, label, pending_full, pending_label, positions, indexed
        if not positions:
            return
        f = model.features(pending_full, args.batch)
        l = model.features(pending_label, args.batch)
        if full is None:
            full = np.full((len(refs), f.shape[1]), np.nan, dtype=np.float32)
            label = np.full_like(full, np.nan)
        full[positions] = f
        label[positions] = l
        indexed += len(positions)
        pending_full, pending_label, positions = [], [], []
        print(json.dumps({'indexed': indexed, 'elapsed_s': round(time.perf_counter()-started, 1)}), flush=True)

    for i, ref in enumerate(refs):
        if ref['slug'] in excluded:
            continue
        region = regions.get(ref['slug'])
        if region is None:
            if ref.get('sha256'):
                raise ValueError('reference image available but no region '+ref['slug'])
            continue
        path = find_image(ref, args.image_dir, ref['slug'])
        if path is None:
            raise FileNotFoundError(ref['slug'])
        image = load_image(path, ref['sha256'])
        pending_full.append(image)
        pending_label.append(image.crop(region['v2_box']))
        positions.append(i)
        if len(positions) >= args.batch:
            flush()
    flush()
    original_available = np.isfinite(base['full']).all(axis=1) & np.isfinite(base['label']).all(axis=1)
    expected_indexed = sum(bool(original_available[i]) and ref['slug'] not in excluded
                           for i, ref in enumerate(refs))
    if indexed != expected_indexed:
        raise ValueError(f'expected {expected_indexed} available refs after gate; got {indexed}')
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out/'index.npz', full=full, label=label, slugs=np.array(slugs))
    info = {
        'version': args.model+VERSION_SUFFIX, 'model': model.model_id+'@'+model.model_rev,
        'full_encoder': model.model_id+'@'+model.model_rev,
        'label_encoder': model.model_id+'@'+model.model_rev,
        'label_crop': base_info['label_crop'],
        'catalog_manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'v2_index_sha256': hashlib.sha256((args.v2_index/'index.npz').read_bytes()).hexdigest(),
        'v2_regions_sha256': hashlib.sha256(args.regions.read_bytes()).hexdigest(),
        'reference_decisions_sha256': hashlib.sha256(decisions_raw).hexdigest(),
        'available_indexed_refs': indexed, 'unavailable_refs': len(refs)-indexed,
        'dimension': full.shape[1], 'elapsed_s': round(time.perf_counter()-started, 2),
    }
    (args.out/'index-info.json').write_text(json.dumps(info, indent=2)+'\n')
    print(json.dumps(info), flush=True)


def make_queries(args):
    manifest_hash, cases = cases_from_manifest(args.manifest)
    if len({x['case_id'] for x in cases}) != len(cases):
        raise ValueError('duplicate query case ID')
    cases = {x['case_id']: x for x in cases}
    visual = read_rows(args.visual)
    fused_rows = read_rows(args.fused)
    old_fused = {x['case_id']: x for x in fused_rows}
    if (len(visual) != len(cases) or len({x['case_id'] for x in visual}) != len(visual)
            or {x['case_id'] for x in visual} != set(cases)
            or len(old_fused) != len(fused_rows) or set(old_fused) != set(cases)):
        raise ValueError('visual/fused/manifest case IDs mismatch')
    info = json.loads((args.index_dir/'index-info.json').read_text())
    expected_model = '@'.join(MODELS[args.model])
    indexed_model = info.get('model')
    if indexed_model is None and info.get('full_encoder') == info.get('label_encoder'):
        indexed_model = info.get('full_encoder')
    if indexed_model != expected_model:
        raise ValueError('index encoder differs from query encoder')
    if info['catalog_manifest_sha256'] != hashlib.sha256(args.catalog.read_bytes()).hexdigest():
        raise ValueError('index catalog hash mismatch')
    index = np.load(args.index_dir/'index.npz')
    full, label, slugs = index['full'], index['label'], list(index['slugs'])
    if slugs != [x['slug'] for x in json.loads(args.catalog.read_text())['references']]:
        raise ValueError('index/catalog slug order mismatch')
    valid_full = np.isfinite(full).all(axis=1)
    valid_label = np.isfinite(label).all(axis=1)
    model = Embedder(args.device, args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, prior in enumerate(visual, 1):
        cid = prior['case_id']; case = cases[cid]
        if prior['query_sha256'] != case['sha256'] or prior['track'] != case['track']:
            raise ValueError('query hash/track mismatch '+cid)
        old = old_fused[cid]
        if old['query_sha256'] != case['sha256']:
            raise ValueError('old OCR lineage mismatch '+cid)
        image = load_image(image_path(args.image_root, case), case['sha256'])
        box = prior['selection']['selected_box']
        whole_rank, label_rank = [], []
        whole_ms = label_ms = 0
        if box is not None:
            target = image if case['track'] == 'retrieval' else image.crop(box)
            region = prior['label_context_box']
            if region is None:
                raise ValueError('selected target lacks label region '+cid)
            t = time.perf_counter()
            vf = model.features([target])[0]
            whole_ms = round((time.perf_counter()-t)*1000)
            t = time.perf_counter()
            vl = model.features([target.crop(region)])[0]
            label_ms = round((time.perf_counter()-t)*1000)
            whole_rank = top(np.where(valid_full, full@vf, np.nan), slugs)
            label_rank = top(np.where(valid_label, label@vl, np.nan), slugs)
        branches = {'whole': whole_rank, 'label': label_rank, 'ocr': old['branches']['ocr']}
        variants = {name: rank_fuse({key: branches[key] for key in subset})
                    for name, subset in VARIANTS.items()}
        predictions = {
            name: ({'action': 'no_match'} if case['track'] == 'service' and box is None
                   else {'slug': rank[0]['slug']} if rank
                   else {'action': 'insufficient_information'})
            for name, rank in variants.items()
        }
        rows.append({
            'case_id': cid, 'track': case['track'], 'status': 'ok',
            'query_sha256': case['sha256'],
            'query_manifest_sha256': manifest_hash, 'version': args.model+VERSION_SUFFIX,
            'model': model.model_id+'@'+model.model_rev,
            'selection': prior['selection'], 'label_context_box': prior['label_context_box'],
            'branches': branches, 'variants_top20': variants,
            'predictions': predictions,
            'whole_embedding_ms': whole_ms, 'label_embedding_ms': label_ms,
        })
        if n % 25 == 0:
            print(json.dumps({'queries': n, 'total': len(visual)}), flush=True)
    args.out.write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rows))
    info = {
        'version': args.model+VERSION_SUFFIX, 'model': model.model_id+'@'+model.model_rev,
        'cases': len(rows),
        'query_manifest_sha256': manifest_hash,
        'v2_visual_sha256': hashlib.sha256(args.visual.read_bytes()).hexdigest(),
        'v2_fused_sha256': hashlib.sha256(args.fused.read_bytes()).hexdigest(),
        'query_index_sha256': hashlib.sha256((args.index_dir/'index.npz').read_bytes()).hexdigest(),
        'embedding_timing_only_not_full_http': True,
    }
    args.out.with_name(args.out.stem+'-lineage.json').write_text(json.dumps(info, indent=2)+'\n')
    print(json.dumps(info), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True, choices=('index', 'queries'))
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--image-dir', type=Path)
    parser.add_argument('--regions', type=Path)
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--v2-index', type=Path)
    parser.add_argument('--index-dir', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--image-root', type=Path)
    parser.add_argument('--visual', type=Path)
    parser.add_argument('--fused', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--model', choices=MODELS, default='so400m384')
    parser.add_argument('--batch', type=int, default=16)
    args = parser.parse_args()
    if args.phase == 'index':
        if not all((args.catalog, args.image_dir, args.regions, args.decisions, args.v2_index)):
            parser.error('index requires catalog, image-dir, regions, decisions, v2-index')
        make_index(args)
    else:
        if not all((args.catalog, args.index_dir, args.manifest, args.image_root,
                    args.visual, args.fused)):
            parser.error('queries require catalog, index-dir, manifest, image-root, visual, fused')
        make_queries(args)


if __name__ == '__main__':
    main()
