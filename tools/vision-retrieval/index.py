"""Build two frozen SigLIP2 visual indexes from public catalog reference images."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from model import Vision, load_image, OWL_ID, OWL_REV, SIGLIP_ID, SIGLIP_REV

def find_image(row, image_dir, identifier):
    original=row.get('path')
    if original and Path(original).is_file():return Path(original)
    if image_dir:
        base=Path(image_dir)
        names=[original,Path(original).name] if original else []
        names += [identifier+e for e in ('.webp','.jpg','.jpeg','.png')]
        for name in names:
            p=(base/name).resolve()
            if not p.is_relative_to(base.resolve()):continue
            if p.is_file():return p
    return None

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--catalog',type=Path,required=True)
    a.add_argument('--image-dir',type=Path)
    a.add_argument('--out',type=Path,required=True)
    a.add_argument('--device',default='cuda')
    a.add_argument('--batch',type=int,default=24)
    a.add_argument('--reuse-full-index',type=Path)
    args=a.parse_args()
    start=time.perf_counter()
    raw=args.catalog.read_bytes();catalog_hash=hashlib.sha256(raw).hexdigest()
    records=json.loads(raw)['references']
    slugs=[r['slug'] for r in records]
    if len(slugs)!=len(set(slugs)):raise ValueError('duplicate catalog slug')
    args.out.mkdir(parents=True,exist_ok=True)
    model=Vision(args.device)
    full=np.full((len(records),768),np.nan,dtype=np.float32)
    label=np.full_like(full,np.nan)
    if args.reuse_full_index:
        prior_info=json.loads((args.reuse_full_index/'index-info.json').read_text())
        prior=np.load(args.reuse_full_index/'index.npz')
        if (prior_info['catalog_manifest_sha256']!=catalog_hash or list(prior['slugs'])!=slugs
            or prior_info['full_encoder']!=SIGLIP_ID+'@'+SIGLIP_REV):
            raise ValueError('reuse index catalog/hash mismatch')
        full=prior['full'].copy();label=np.full_like(full,np.nan)
    missing=[];completed=0;label_sources={};label_records=[]
    for offset in range(0,len(records),args.batch):
        chunk=records[offset:offset+args.batch]
        images=[];bands=[];indices=[]
        for j,row in enumerate(chunk,offset):
            path=find_image(row,args.image_dir,row['slug'])
            if path is None or not row.get('sha256'):
                missing.append({'slug':row['slug'],'reason':'no verified reference'});continue
            image=load_image(path,row['sha256'])
            region,choice=model.label_region(image)
            images.append(image);bands.append(region);indices.append(j)
            label_sources[choice['source']]=label_sources.get(choice['source'],0)+1
            label_records.append({'slug':row['slug'],'source':choice['source'],'box':choice['box'],
                                  'score':choice['score'],'detect_ms':choice['detect_ms']})
        if images:
            full_vec=model.image_features(images,args.batch) if not args.reuse_full_index else full[indices]
            label_vec=model.image_features(bands,args.batch)
            if full_vec.shape[1]!=full.shape[1]:
                if completed==0:
                    full=np.full((len(records),full_vec.shape[1]),np.nan,dtype=np.float32)
                    label=np.full_like(full,np.nan)
                else:raise ValueError('feature dimension changed')
            full[indices]=full_vec;label[indices]=label_vec;completed+=len(indices)
        print(json.dumps({'indexed':completed,'catalog_total':len(records),'elapsed_s':round(time.perf_counter()-start,2)}),flush=True)
    np.savez_compressed(args.out/'index.npz',full=full,label=label,slugs=np.array(slugs))
    info={'catalog_manifest_sha256':catalog_hash,'catalog_size':len(records),'visual_refs':completed,'missing':missing,
          'full_encoder':SIGLIP_ID+'@'+SIGLIP_REV,'label_encoder':SIGLIP_ID+'@'+SIGLIP_REV,
          'label_crop':'OWLv2 open-vocabulary label prompts with documented geometric fallback',
          'label_sources':label_sources,'reused_full_index':str(args.reuse_full_index) if args.reuse_full_index else None,
          'detector':OWL_ID+'@'+OWL_REV,'elapsed_s':round(time.perf_counter()-start,2)}
    (args.out/'index-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    (args.out/'label-regions.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in label_records))
    print(json.dumps({'complete':True,'visual_refs':completed,'missing_refs':len(missing),'elapsed_s':info['elapsed_s']}),flush=True)
if __name__=='__main__':main()
