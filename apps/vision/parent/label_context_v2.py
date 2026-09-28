"""One-variable label-context ablation over frozen v1 detections.

Reuse v1 bottle choice, detector boxes, whole embeddings, OCR target bytes and
fusion rules. Only widen the label crop before the shared visual encoder.
Neither catalog answers nor evaluation gold are inputs.
"""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from model import Vision, load_image, SIGLIP_ID, SIGLIP_REV
from index import find_image
from ranking import top

VERSION = 'owlv2-label-context-union-v2'

def context_box(size, detected):
    """Union OWLv2 box with broad central/lower label design context."""
    w, h = size
    anchor = [round(.06*w), round(.30*h), round(.94*w), round(.92*h)]
    if detected is None:
        return anchor
    x0, y0, x1, y1 = [int(v) for v in detected]
    return [max(0, min(anchor[0], x0)), max(0, min(anchor[1], y0)),
            min(w, max(anchor[2], x1)), min(h, max(anchor[3], y1))]

def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def make_index(a):
    start = time.perf_counter()
    raw = a.catalog.read_bytes()
    refs = json.loads(raw)['references']
    slugs = [r['slug'] for r in refs]
    info = json.loads((a.v1_index/'index-info.json').read_text())
    if (info['catalog_manifest_sha256'] != hashlib.sha256(raw).hexdigest()
            or info['full_encoder'] != SIGLIP_ID+'@'+SIGLIP_REV):
        raise ValueError('v1 catalog or encoder mismatch')
    previous = np.load(a.v1_index/'index.npz')
    if list(previous['slugs']) != slugs:
        raise ValueError('catalog/index slug order mismatch')
    choices = {x['slug']:x for x in read_jsonl(a.v1_index/'label-regions.jsonl')}
    if len(choices) != info['visual_refs']:
        raise ValueError('missing v1 label choices')
    model = Vision(a.device)
    full = previous['full'].copy()
    label = np.full_like(full, np.nan)
    diagnostics = []
    pending, positions = [], []
    for j, ref in enumerate(refs):
        if ref['slug'] not in choices:
            if ref.get('sha256'):
                raise ValueError('verified reference lacks v1 label '+ref['slug'])
            continue
        path = find_image(ref, a.image_dir, ref['slug'])
        if path is None:
            raise FileNotFoundError(ref['slug'])
        image = load_image(path, ref['sha256'])
        choice = choices[ref['slug']]
        box = context_box(image.size, choice['box'])
        pending.append(image.crop(box)); positions.append(j)
        diagnostics.append({'slug':ref['slug'],'v1_box':choice['box'],'v2_box':box,
                            'image_size':list(image.size)})
        if len(pending) >= a.batch:
            label[positions] = model.image_features(pending, a.batch)
            pending, positions = [], []
            if j % 240 < a.batch:
                print(json.dumps({'indexed':j+1,'elapsed_s':round(time.perf_counter()-start,1)}), flush=True)
    if pending:
        label[positions] = model.image_features(pending, a.batch)
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out/'index.npz', full=full, label=label, slugs=np.array(slugs))
    index_info = {**info,'label_crop':VERSION,'v1_index':str(a.v1_index),
                  'v1_index_sha256':hashlib.sha256((a.v1_index/'index.npz').read_bytes()).hexdigest(),
                  'visual_refs':len(diagnostics),'elapsed_s':round(time.perf_counter()-start,2)}
    (a.out/'index-info.json').write_text(json.dumps(index_info,ensure_ascii=False,indent=2)+'\n')
    (a.out/'label-regions.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in diagnostics))
    print(json.dumps({'indexed':len(diagnostics),'elapsed_s':index_info['elapsed_s']}), flush=True)

def make_queries(a):
    start = time.perf_counter()
    manifest = json.loads(a.queries.read_text())
    cases = {c['case_id']:c for c in manifest['cases']}
    old = read_jsonl(a.v1_visual)
    index_info = json.loads((a.index_dir/'index-info.json').read_text())
    if index_info['v1_index_sha256'] != hashlib.sha256((a.v1_index/'index.npz').read_bytes()).hexdigest():
        raise ValueError('v2 index parent mismatch')
    arr = np.load(a.index_dir/'index.npz')
    slugs = list(arr['slugs']); label = arr['label']
    model = Vision(a.device)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'crops').mkdir(exist_ok=True)
    output = []
    for n, row in enumerate(old, 1):
        cid = row['case_id']; case = cases[cid]
        if row['query_sha256'] != case['sha256'] or row['track'] != case['track']:
            raise ValueError('v1 query lineage mismatch '+cid)
        updated = {**row,'preprocess_version':VERSION,'index_info':str(a.index_dir/'index-info.json')}
        stage = dict(row['timings_ms']); updated['timings_ms'] = stage
        if row['target_path']:
            path = find_image(case,a.query_dir,cid)
            if path is None:
                raise FileNotFoundError(cid)
            image = load_image(path,case['sha256'])
            target = image if case['track']=='retrieval' else image.crop(row['selection']['selected_box'])
            choice = row['label_selection']
            detected = None if row['selection']['selection_reason']=='standalone_label_no_bottle' else choice['box']
            box = context_box(target.size, detected)
            crop = target.crop(box)
            crop_path = a.out/'crops'/(cid+'-label-context.jpg')
            crop.save(crop_path,'JPEG',quality=92)
            t = time.perf_counter(); feature = model.image_features([crop])[0]
            embed_ms = round((time.perf_counter()-t)*1000)
            score = np.where(np.isfinite(label).all(axis=1), label @ feature, np.nan)
            updated['label_top20'] = top(score,slugs)
            updated['label_crop_path'] = str(crop_path)
            updated['label_context_box'] = box
            stage['v1_label_embedding_ms'] = stage['label_embedding_ms']
            stage['label_embedding_ms'] = embed_ms
            stage['total_ms'] = stage['total_ms'] - stage['v1_label_embedding_ms'] + embed_ms
        else:
            updated['label_context_box'] = None
        output.append(updated)
        if n % 25 == 0:
            print(json.dumps({'queries':n,'elapsed_s':round(time.perf_counter()-start,1)}),flush=True)
    (a.out/'visual.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in output))
    (a.out/'lineage.json').write_text(json.dumps({
        'label_context_version':VERSION,
        'v1_visual_sha256':hashlib.sha256(a.v1_visual.read_bytes()).hexdigest(),
        'v2_index_sha256':hashlib.sha256((a.index_dir/'index.npz').read_bytes()).hexdigest(),
        'query_manifest_sha256':hashlib.sha256(a.queries.read_bytes()).hexdigest(),
        'query_count':len(output)},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'queries':len(output),'elapsed_s':round(time.perf_counter()-start,2)}),flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--phase',choices=('index','queries'),required=True)
    p.add_argument('--catalog',type=Path); p.add_argument('--image-dir',type=Path)
    p.add_argument('--v1-index',type=Path,required=True); p.add_argument('--index-dir',type=Path)
    p.add_argument('--queries',type=Path); p.add_argument('--query-dir',type=Path)
    p.add_argument('--v1-visual',type=Path); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--device',default='cuda'); p.add_argument('--batch',type=int,default=24)
    a = p.parse_args()
    if a.phase == 'index':
        if not a.catalog or not a.image_dir: p.error('index requires catalog and image-dir')
        make_index(a)
    else:
        if not a.queries or not a.query_dir or not a.v1_visual or not a.index_dir:
            p.error('queries requires queries, query-dir, v1-visual, index-dir')
        make_queries(a)
if __name__ == '__main__':main()
