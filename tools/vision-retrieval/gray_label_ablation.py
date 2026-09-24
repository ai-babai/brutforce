"""Untrained grayscale label branch over the frozen OWLv2 v2 selections.

It keeps detector boxes, whole-image ranks, OCR ranks, fusion weights and
catalog slug order fixed. The grayscale label index is built from the same
2,080 verified reference crops, converting L back to RGB for SigLIP2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import ImageOps

from detector_run import cases_from_manifest, image_path
from fuse import VARIANTS, rank_fuse
from index import find_image
from model import SIGLIP_ID, SIGLIP_REV, load_image
from ranking import top

VERSION = 'siglip2-grayscale-label-20260925'


class Embedder:
    def __init__(self, device):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.torch = torch
        self.device = device if device != 'cuda' or torch.cuda.is_available() else 'cpu'
        self.embed_processor = AutoProcessor.from_pretrained(SIGLIP_ID, revision=SIGLIP_REV)
        self.embedder = AutoModel.from_pretrained(
            SIGLIP_ID, revision=SIGLIP_REV, use_safetensors=True
        ).to(self.device).eval()

    def image_features(self, images, batch_size=24):
        import torch.nn.functional as F
        if not images:
            return np.empty((0, 768), dtype=np.float32)
        outputs = []
        for i in range(0, len(images), batch_size):
            inputs = self.embed_processor(images=images[i:i+batch_size], return_tensors='pt').to(self.device)
            with self.torch.inference_mode():
                value = self.embedder.get_image_features(**inputs)
                if not isinstance(value, self.torch.Tensor):
                    value = value.pooler_output
                outputs.append(F.normalize(value.float(), dim=-1).cpu())
        if self.device.startswith('cuda'):
            self.torch.cuda.synchronize()
        return self.torch.cat(outputs).numpy()


def grayscale(image):
    return ImageOps.grayscale(image).convert('RGB')


def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def paired_rank(color, gray):
    scores = {}
    for branch in (color, gray):
        for rank, row in enumerate(branch, 1):
            slug = row['slug']
            scores[slug] = scores.get(slug, 0) + .5/(60+rank)
    return [{'slug': slug, 'score': round(score, 7)}
            for slug, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:20]]


def make_index(args):
    raw = args.catalog.read_bytes()
    refs = json.loads(raw)['references']
    slugs = [r['slug'] for r in refs]
    prior = np.load(args.v2_index/'index.npz')
    info = json.loads((args.v2_index/'index-info.json').read_text())
    if (list(prior['slugs']) != slugs
            or info['catalog_manifest_sha256'] != hashlib.sha256(raw).hexdigest()):
        raise ValueError('catalog/index mismatch')
    regions = {x['slug']: x for x in read_jsonl(args.regions)}
    if len(regions) != info['visual_refs']:
        raise ValueError('reference-region count mismatch')
    model = Embedder(args.device)
    label = np.full_like(prior['label'], np.nan)
    pending, positions = [], []
    started = time.perf_counter()
    for i, ref in enumerate(refs):
        region = regions.get(ref['slug'])
        if region is None:
            if ref.get('sha256'):
                raise ValueError('verified reference has no crop')
            continue
        path = find_image(ref, args.image_dir, ref['slug'])
        if path is None:
            raise FileNotFoundError(ref['slug'])
        image = load_image(path, ref['sha256'])
        pending.append(grayscale(image.crop(region['v2_box'])))
        positions.append(i)
        if len(pending) >= args.batch:
            label[positions] = model.image_features(pending, args.batch)
            pending, positions = [], []
            if i % 240 < args.batch:
                print(json.dumps({'indexed': i+1}), flush=True)
    if pending:
        label[positions] = model.image_features(pending, args.batch)
    args.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out/'gray-label.npz', label=label, slugs=np.array(slugs))
    manifest = {
        'version': VERSION, 'catalog_manifest_sha256': hashlib.sha256(raw).hexdigest(),
        'v2_index_sha256': hashlib.sha256((args.v2_index/'index.npz').read_bytes()).hexdigest(),
        'regions_sha256': hashlib.sha256(args.regions.read_bytes()).hexdigest(),
        'encoder': SIGLIP_ID+'@'+SIGLIP_REV,
        'verified_refs': len(regions), 'missing_refs': len(refs)-len(regions),
        'elapsed_s': round(time.perf_counter()-started, 2),
    }
    (args.out/'gray-index-info.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest), flush=True)


def make_queries(args):
    manifest_hash, cases = cases_from_manifest(args.manifest)
    cases = {x['case_id']: x for x in cases}
    visual = read_jsonl(args.visual)
    fused = {x['case_id']: x for x in read_jsonl(args.fused)}
    index = np.load(args.index_dir/'gray-label.npz')
    slugs = list(index['slugs'])
    label = index['label']
    if len(visual) != len(cases) or list(np.load(args.v2_index/'index.npz')['slugs']) != slugs:
        raise ValueError('query or slug count mismatch')
    model = Embedder(args.device)
    args.out.mkdir(parents=True, exist_ok=True)
    gray_rows, pair_rows = [], []
    for i, row in enumerate(visual, 1):
        cid = row['case_id']; case = cases[cid]
        if row['query_sha256'] != case['sha256'] or row['track'] != case['track']:
            raise ValueError('query lineage mismatch '+cid)
        old = fused[cid]
        if old['query_sha256'] != case['sha256']:
            raise ValueError('fused lineage mismatch '+cid)
        image = load_image(image_path(args.image_root, case), case['sha256'])
        box = row['selection']['selected_box']
        gray_rank = []
        gray_ms = 0
        if box is not None:
            target = image if case['track'] == 'retrieval' else image.crop(box)
            context = row['label_context_box']
            if context is None:
                raise ValueError('selected target lacks context box '+cid)
            crop = grayscale(target.crop(context))
            t = time.perf_counter()
            vector = model.image_features([crop])[0]
            gray_ms = round((time.perf_counter()-t)*1000)
            scores = np.where(np.isfinite(label).all(axis=1), label@vector, np.nan)
            gray_rank = top(scores, slugs)
        for mode, branch, dest in (
            ('gray', gray_rank, gray_rows),
            ('color_gray_equal_rrf60', paired_rank(row['label_top20'], gray_rank), pair_rows),
        ):
            branches = {'whole': row['whole_top20'], 'label': branch,
                        'ocr': old['branches']['ocr']}
            variants = {name: rank_fuse({key: branches[key] for key in subset})
                        for name, subset in VARIANTS.items()}
            predictions = {
                name: ({'action': 'no_match'} if case['track'] == 'service' and box is None
                       else {'slug': rank[0]['slug']} if rank
                       else {'action': 'insufficient_information'})
                for name, rank in variants.items()
            }
            dest.append({
                'case_id': cid, 'track': case['track'], 'query_sha256': case['sha256'],
                'query_manifest_sha256': manifest_hash, 'version': VERSION,
                'mode': mode, 'selected_box': box, 'label_context_box': row['label_context_box'],
                'branches': branches, 'variants_top20': variants,
                'predictions': predictions, 'gray_embedding_ms': gray_ms,
                'color_label_top20': row['label_top20'],
            })
        if i % 25 == 0:
            print(json.dumps({'queries': i, 'total': len(visual)}), flush=True)
    for name, rows in (('gray', gray_rows), ('color-gray', pair_rows)):
        (args.out/(name+'.jsonl')).write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rows))
    info = {
        'version': VERSION, 'query_manifest_sha256': manifest_hash,
        'v2_visual_sha256': hashlib.sha256(args.visual.read_bytes()).hexdigest(),
        'v2_fused_sha256': hashlib.sha256(args.fused.read_bytes()).hexdigest(),
        'gray_index_sha256': hashlib.sha256((args.index_dir/'gray-label.npz').read_bytes()).hexdigest(),
        'cases': len(visual), 'measured_gray_embedding_ms_only': True,
        'no_full_http_timing_claim': True,
    }
    (args.out/'lineage.json').write_text(json.dumps(info, indent=2)+'\n')
    print(json.dumps(info), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True, choices=('index', 'queries'))
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--image-dir', type=Path)
    parser.add_argument('--regions', type=Path)
    parser.add_argument('--v2-index', type=Path, required=True)
    parser.add_argument('--index-dir', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--image-root', type=Path)
    parser.add_argument('--visual', type=Path)
    parser.add_argument('--fused', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--batch', type=int, default=24)
    args = parser.parse_args()
    if args.phase == 'index':
        if not args.catalog or not args.image_dir or not args.regions:
            parser.error('index needs catalog, image-dir and regions')
        make_index(args)
    else:
        if not all((args.index_dir, args.manifest, args.image_root,
                    args.visual, args.fused)):
            parser.error('queries need index-dir, manifest, image-root, visual and fused')
        make_queries(args)


if __name__ == '__main__':
    main()
