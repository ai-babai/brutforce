#!/usr/bin/env python3
"""Deterministic, non-neural pilot variants; never counted as AI generations."""
import argparse,fcntl,hashlib,json,time
from pathlib import Path
from PIL import Image,ImageEnhance,ImageFilter,__version__ as pillow_version
from generate import rows,upsert_manifest,safe_root,checked_image

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=safe_root(a.root)
 with (root/'runs/generation-run.lock').open('a') as runlock:
  fcntl.flock(runlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  augment(root)

def augment(root):
 manifest=rows(root/'manifest.jsonl');lookup={x['image_id']:x for x in manifest};qc={}
 for x in rows(root/'qc-deepseek.jsonl'):
  if x.get('qa_version','').endswith('v2') and x.get('status')=='completed':qc[x['output_image_id']]=x
 selected={}
 for row in manifest:
  review=qc.get(row['image_id'],{});judge=review.get('judgement',{})
  if row['role']=='output' and review and review.get('output_sha256')!=row['sha256']:
   raise ValueError('stale QA '+row['image_id'])
  if row['role']=='output' and judge.get('identity_correct')=='yes' and judge.get('suggested_qc')=='accepted' and row['slug'] not in selected:
   checked_image(root,row)
   selected[row['slug']]=row
 transformations=[('roll12',{'rotation_clockwise_deg':12}),('exposure_low',{'brightness_factor':0.48}),('crop_blur',{'crop_fraction':[0.12,0.08,0.90,0.94],'gaussian_blur_radius_px':1.1})]
 for parent in selected.values():
  for name,params in transformations:
   image_id='aug-'+hashlib.sha256(parent['image_id'].encode()).hexdigest()[:12]+'-'+name
   if image_id in lookup:
    existing=lookup[image_id]
    if existing.get('parent_ids')!=[parent['image_id']]:raise ValueError('augmentation parent mismatch '+image_id)
    checked_image(root,existing)
    continue
   start=time.monotonic();im=Image.open(checked_image(root,parent)).convert('RGB')
   if name=='roll12':im=im.rotate(-12,resample=Image.Resampling.BICUBIC,expand=False)
   elif name=='exposure_low':im=ImageEnhance.Brightness(im).enhance(params['brightness_factor'])
   else:
    w,h=im.size;b=params['crop_fraction'];im=im.crop((round(w*b[0]),round(h*b[1]),round(w*b[2]),round(h*b[3]))).filter(ImageFilter.GaussianBlur(params['gaussian_blur_radius_px']))
   path=Path('augmentations')/(image_id+'.png');(root/path).parent.mkdir(exist_ok=True);im.save(root/path)
   thumb=Path('thumbs')/(image_id+'.webp');(root/thumb).parent.mkdir(exist_ok=True);small=im.copy();small.thumbnail((384,384));small.save(root/thumb,'WEBP',quality=85)
   row={'image_id':image_id,'slug':parent['slug'],'role':'augmentation','path':str(path),'thumbnail_path':str(thumb),'origin':'augmentation','scenario_ids':['digital_'+name],'identity_reference_id':parent['identity_reference_id'],'scene_reference_id':parent['scene_reference_id'],'parent_ids':[parent['image_id']],'split':'pilot','requested_conditions':params,'observed_conditions':{'deterministic_transform':name,'parameters':params,'physical_scene_inference':'not asserted'},'provider':'local Pillow','model':'','cost_usd':0,'latency_ms':round((time.monotonic()-start)*1000),'sha256':hashlib.sha256((root/path).read_bytes()).hexdigest(),'qc':{'status':'pending','reason':'Deterministic transform of a provisionally AI-QA-accepted source; human visual review pending. Inherits any parent artifacts.'},'source':{'tool':'Pillow','version':pillow_version,'transform':name,'parameters':params,'source_sha256':parent['sha256'],'api_cost_usd':0}}
   upsert_manifest(root/'manifest.jsonl',row)
 print(json.dumps({'wines':len(selected),'new_variants_max':len(selected)*len(transformations),'api_cost_usd':0}))
if __name__=='__main__':main()
