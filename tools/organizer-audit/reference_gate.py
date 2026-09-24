"""Create a new visual index with explicitly quarantined references disabled.

No photo, slug, query prediction or old index is mutated. Text catalog remains full.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def apply_gate(catalog, index_slugs, arrays, decisions):
    refs={r['slug']:r for r in catalog['references']}
    if list(index_slugs)!=[r['slug'] for r in catalog['references']]:
        raise ValueError('catalog and index slug order differ')
    output={name:value.copy() for name,value in arrays.items()}
    seen=set();log=[]
    for decision in decisions['excluded']:
        slug=decision['slug']
        if slug in seen:raise ValueError('duplicate exclusion slug')
        seen.add(slug)
        if slug not in refs:raise ValueError('unknown exclusion slug')
        if not decision.get('sha256') or refs[slug].get('sha256')!=decision['sha256']:
            raise ValueError('exclusion does not match current reference SHA')
        if not decision.get('reason') or not decision.get('evidence'):
            raise ValueError('exclusion needs reason and evidence')
        idx=list(index_slugs).index(slug)
        before={name:bool(np.isfinite(values[idx]).all()) for name,values in output.items()}
        for values in output.values():values[idx]=np.nan
        log.append({**decision,'previously_finite':before})
    return output,log


def main():
    p=argparse.ArgumentParser()
    for name in ['catalog','index','decisions','out']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('output exists; select a new index version')
    info=json.loads((a.index/'index-info.json').read_text())
    if info['catalog_manifest_sha256']!=digest(a.catalog):
        raise ValueError('catalog bytes do not match source index provenance')
    catalog=json.loads(a.catalog.read_text());decisions=json.loads(a.decisions.read_text())
    raw=np.load(a.index/'index.npz',allow_pickle=False)
    slugs=raw['slugs'];arrays={name:raw[name] for name in raw.files if name!='slugs'}
    if set(arrays)!={'full','label'}:raise ValueError('unknown source index layout')
    masked,log=apply_gate(catalog,slugs,arrays,decisions)
    a.out.mkdir(parents=True)
    np.savez_compressed(a.out/'index.npz',slugs=slugs,**masked)
    available=np.isfinite(masked['full']).all(axis=1)&np.isfinite(masked['label']).all(axis=1)
    info['visual_refs']=int(available.sum())
    info['missing']=[{'slug':str(slug),'reason':'quarantined by reference gate' if str(slug) in {r['slug'] for r in log} else 'pre-existing unavailable reference'} for slug,ok in zip(slugs,available) if not ok]
    info['reference_gate']={'version':decisions['version'],'decision_sha256':digest(a.decisions),'source_index_sha256':digest(a.index/'index.npz'),'excluded':len(log),'text_catalog_unchanged':True}
    (a.out/'index-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    (a.out/'reference-decisions.json').write_text(json.dumps({'version':decisions['version'],'excluded':log},ensure_ascii=False,indent=2)+'\n')
    if (a.index/'label-regions.jsonl').exists():shutil.copyfile(a.index/'label-regions.jsonl',a.out/'label-regions.jsonl')
    print(json.dumps({'visual_refs':int(available.sum()),'missing':int((~available).sum()),'excluded':len(log),'new_index_sha256':digest(a.out/'index.npz')}))

if __name__=='__main__':main()
