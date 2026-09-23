#!/usr/bin/env python3
"""Bounded OpenRouter two-reference image edit pilot. User-authorized API experiment.
No keys or encoded images are written to request logs. Outputs are outside Git.
"""
import fcntl
import argparse,base64,concurrent.futures,datetime,hashlib,io,json,os,re,threading,time,urllib.request,urllib.error
from pathlib import Path
from PIL import Image

MODELS={
 'qwen':('qwen/qwen-image-3','alibaba',0.06),
 'banana':('google/gemini-3.1-flash-image','google-ai-studio',0.20),
 'flux':('black-forest-labs/flux.2-pro','black-forest-labs',0.16),
}
KEY=Path('/Users/skif/skif-os/v001/secrets/agent-ops/values/brutforce/lct-openrouter-api-key')
LOCK=threading.Lock()
FROZEN_EVAL=Path('/Users/skif/ml-data/brutforce/eval-v1')
def safe_root(root):
 root=root.resolve()
 if root==FROZEN_EVAL or FROZEN_EVAL in root.parents:
  raise ValueError('Refusing to write inside the frozen evaluation corpus')
 return root
def checked_image(root,row):
 p=(root/row['path']).resolve()
 if not p.is_relative_to(root) or not p.is_file():raise ValueError('missing/unsafe image '+row['image_id'])
 if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('hash mismatch '+row['image_id'])
 return p
def rows(p):
 return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
def append(p,x):
 with p.open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def upsert_manifest(p,row):
 # Separate lock file survives atomic replacement and coordinates writers.
 with p.with_suffix('.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  current=rows(p)
  matched=[x for x in current if x['image_id']==row['image_id']]
  if matched and any(x.get('sha256')!=row.get('sha256') for x in matched):
   raise ValueError('Refusing to overwrite existing output identity with different bytes')
  current=[x for x in current if x['image_id']!=row['image_id']]+[row]
  temp=p.with_suffix('.next')
  with temp.open('w') as f:
   f.write(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in current));f.flush();os.fsync(f.fileno())
  os.replace(temp,p)

def iso():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dataurl(p):
 im=Image.open(p).convert('RGB');im.thumbnail((1000,1000))
 b=io.BytesIO();im.save(b,'JPEG',quality=95)
 return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode(), im.size

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--models',default='qwen,banana,flux');ap.add_argument('--job-ids',default='');ap.add_argument('--limit',type=int,default=100);ap.add_argument('--workers',type=int,default=2);ap.add_argument('--budget',type=float,default=10);ap.add_argument('--dry-run',action='store_true');ap.add_argument('--retry-errors',action='store_true')
 a=ap.parse_args();root=safe_root(a.root); run=root/'runs';run.mkdir(exist_ok=True,parents=True)
 runlock=(run/'generation-run.lock').open('a')
 try:fcntl.flock(runlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('Another generation runner holds the corpus lock')
 ledger=run/'generation-ledger.jsonl';manifest=root/'manifest.jsonl'
 refs={r['image_id']:r for r in rows(manifest)};jobs=rows(root/'jobs.jsonl')
 if a.job_ids:jobs=[j for j in jobs if j['job_id'] in set(a.job_ids.split(','))]
 old=rows(ledger)
 # Reconcile durable artifacts before any paid retry. Missing bytes or an uncertain
 # reservation need manual investigation; a retry could pay twice.
 finished=set()
 for rid,r in refs.items():
  if r.get('role')=='output':checked_image(root,r);finished.add(rid)
 completed_manifest=set(finished)
 states={r['attempt_id']:r for r in old};uncertain=set()
 for r in states.values():
  if r['status']=='complete' and r['output_id'] not in finished:
   raise ValueError('completed paid call missing from manifest: '+r['output_id'])
  if r['status']=='reserved':finished.add(r['output_id']);uncertain.add(r['output_id'])
  if not a.retry_errors and r['status'] in ('http_error','error'):finished.add(r['output_id'])
 # Reservations left after process loss count conservatively. A persisted completed row replaces its reservation.
 spent=sum(float(r.get('cost_usd',r.get('reserve_usd',0))) for r in states.values())
 state={'spent':spent,'reserved':0,'stop':False}
 tasks=[]
 for j in jobs:
  for field,role in (('identity_reference_id','identity_reference'),('scene_reference_id','scene_reference')):
   ref=refs.get(j[field])
   if ref is None or ref.get('role')!=role:raise ValueError('missing/wrong '+role+' for '+j['job_id'])
   checked_image(root,ref)
  for alias in a.models.split(','):
   if alias not in MODELS:raise ValueError('unknown model alias')
   outid=j['job_id']+'--'+alias
   if outid in refs and refs[outid].get('role')!='output':
    raise ValueError('output id collides with non-output row: '+outid)
   if outid not in refs and any((root/'images'/(outid+'.'+ext)).exists() for ext in ('png','jpg','webp')):
    raise ValueError('orphan image requires manual ledger reconciliation: '+outid)
   if outid not in finished:tasks.append((j,alias,outid))
 tasks=tasks[:a.limit]
 print(json.dumps({'pending':len(tasks),'blocked_uncertain_reservations':len(uncertain-completed_manifest),'spent_or_uncertain_usd':spent,'cap':a.budget,'dry_run':a.dry_run}),flush=True)
 if a.dry_run:return
 key=KEY.read_text().strip()
 def call(task):
  j,alias,outid=task; model,provider,reserve=MODELS[alias]
  refrows=[refs[j['identity_reference_id']],refs[j['scene_reference_id']]]
  inputs=[];sizes=[]
  for r in refrows:
   p=checked_image(root,r)
   url,sz=dataurl(p);inputs.append({'type':'image_url','image_url':{'url':url}});sizes.append(sz)
  body={'model':model,'prompt':j['prompt'],'input_references':inputs,'n':1,'aspect_ratio':'1:1','provider':{'only':[provider],'allow_fallbacks':False}}
  if alias!='flux':body['resolution']='1K'
  else:body['size']='1024x1024'
  attempt=outid+'-'+str(time.time_ns())
  with LOCK:
   if state['stop'] or state['spent']+state['reserved']+reserve>a.budget:
    print('BUDGET_STOP '+outid,flush=True);return
   state['reserved']+=reserve
   append(ledger,{'attempt_id':attempt,'output_id':outid,'status':'reserved','reserve_usd':reserve,'timestamp':iso(),'model':model})
  redacted={k:v for k,v in body.items() if k!='input_references'};redacted.update({'reference_ids':[r['image_id'] for r in refrows],'input_sizes':sizes})
  (run/(attempt+'-request.json')).write_text(json.dumps(redacted,ensure_ascii=False,indent=2))
  start=time.monotonic();cost=reserve;record={'attempt_id':attempt,'output_id':outid,'job_id':j['job_id'],'timestamp':iso(),'model':model,'provider':provider}
  try:
   req=urllib.request.Request('https://openrouter.ai/api/v1/images',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=260) as response: answer=json.load(response)
   usage=answer.get('usage',{});actual=usage.get('cost');cost=float(actual) if actual is not None else reserve
   outputs=answer.get('data',[])
   if len(outputs)!=1:raise ValueError('Expected exactly one output image')
   raw=base64.b64decode(outputs[0]['b64_json']);im=Image.open(io.BytesIO(raw));im.load()
   if im.format not in ('PNG','JPEG','WEBP'):raise ValueError('unexpected image format')
   ext={'PNG':'png','JPEG':'jpg','WEBP':'webp'}[im.format]
   path=Path('images')/(outid+'.'+ext);(root/path).parent.mkdir(exist_ok=True);(root/path).write_bytes(raw)
   thumb=Path('thumbs')/(outid+'.webp');(root/thumb).parent.mkdir(exist_ok=True)
   small=im.convert('RGB');small.thumbnail((384,384));small.save(root/thumb,'WEBP',quality=85)
   ms=round((time.monotonic()-start)*1000)
   record.update(status='complete',cost_usd=cost,cost_verified=actual is not None,usage=usage,latency_ms=ms,path=str(path),size=im.size,sha256=hashlib.sha256(raw).hexdigest())
   row={'image_id':outid,'slug':j['slug'],'role':'output','path':str(path),'thumbnail_path':str(thumb),'origin':'ai_edited','scenario_ids':j.get('scenario_ids',[]),'identity_reference_id':j['identity_reference_id'],'scene_reference_id':j['scene_reference_id'],'requested_conditions':j.get('requested_conditions',{}),'observed_conditions':{},'model':model,'provider':provider,'cost_usd':cost,'latency_ms':ms,'qc':{'status':'pending','reason':'Awaiting independent visual identity and condition check'},'split':'pilot','parent_ids':[r['image_id'] for r in refrows],'sha256':record['sha256'],'source':{'job_id':j['job_id'],'attempt_id':attempt,'prompt_ref':'runs/'+attempt+'-request.json','cost_verified':actual is not None}}
   # Persist provider metadata without base64 image payload.
   safe={k:v for k,v in answer.items() if k!='data'};(run/(attempt+'-response.json')).write_text(json.dumps(safe,ensure_ascii=False,indent=2))
   with LOCK:upsert_manifest(manifest,row)
  except urllib.error.HTTPError as e:
   # Docs specify failed image calls are not billed; retain uncertainty until account reconciliation.
   record.update(status='http_error',http_status=e.code,error=e.read(4096).decode(errors='replace'),cost_usd=reserve,cost_verified=False,latency_ms=round((time.monotonic()-start)*1000))
  except Exception as e:
   record.update(status='error',error=type(e).__name__+': '+str(e)[:400],cost_usd=cost,cost_verified=False,latency_ms=round((time.monotonic()-start)*1000))
  with LOCK:
   state['reserved']-=reserve;state['spent']+=cost
   if cost>reserve:state['stop']=True
   append(ledger,record)
   print(json.dumps({'output_id':outid,'status':record['status'],'cost_usd':cost,'latency_ms':record.get('latency_ms'),'spent_or_reserved_usd':round(state['spent']+state['reserved'],5),'error':record.get('error','')[:200]}),flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:list(pool.map(call,tasks))
 print(json.dumps({'final_spent_or_uncertain_usd':state['spent']}),flush=True)
if __name__=='__main__':main()
