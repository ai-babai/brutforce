"""Prepared final C05 CPU bridge; check-only default, no public deployment."""
import hashlib,json,os,queue,resource,signal,sys,threading,time
from concurrent.futures import Future
from email import policy as mime_policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PIL import UnidentifiedImageError
from urllib.parse import parse_qs,urlsplit
TRACE_CODE=Path(__file__).resolve().parent
HERE=Path('/srv/lct/data/experiments/batch32-simple84-production-20261002')
sys.dont_write_bytecode=True

def sha(path):
 with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

class MainThreadDispatcher:
 """Bounded HTTP-to-owner handoff; only initialization/main thread executes work."""
 def __init__(self,max_pending=2):
  if threading.current_thread() is not threading.main_thread():raise RuntimeError('Model owner must be main initialization thread')
  self.owner_ident=threading.get_ident();self.owner_native_id=threading.get_native_id()
  self.pending=queue.Queue(maxsize=max_pending);self.state_lock=threading.Lock();self.closed=False;self.active=False
 def submit(self,work):
  future=Future()
  with self.state_lock:
   if self.closed:raise RuntimeError('Model owner is stopping')
   self.pending.put_nowait((future,work))
  return future
 def run_once(self,timeout=.2):
  if threading.get_ident()!=self.owner_ident:raise RuntimeError('Inference execution left initialization thread')
  try:future,work=self.pending.get(timeout=timeout)
  except queue.Empty:return False
  try:
   with self.state_lock:
    if self.closed:
     if not future.done():future.set_exception(RuntimeError('Model owner is stopping'))
     return False
    self.active=True
   if future.set_running_or_notify_cancel():
    try:future.set_result(work())
    except BaseException as exc:
     future.set_exception(exc if isinstance(exc,Exception) else RuntimeError('Model owner interrupted'))
     if not isinstance(exc,Exception):raise
   return True
  finally:
   self.active=False;self.pending.task_done()
 def run(self):
  while not self.closed:self.run_once()
 def close(self):
  with self.state_lock:
   self.closed=True
   while True:
    try:future,_=self.pending.get_nowait()
    except queue.Empty:break
    if not future.done():future.set_exception(RuntimeError('Model owner is stopping'))
    self.pending.task_done()
 def health(self):
  return dict(owner_ident=self.owner_ident,owner_native_id=self.owner_native_id,queue_limit=self.pending.maxsize,queued=self.pending.qsize(),active=self.active,stopping=self.closed)

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--serve-private',action='store_true');parser.add_argument('--check-only',action='store_true');parser.add_argument('--port',type=int);parser.add_argument('--runtime');parser.add_argument('--base',default=str(HERE));args=parser.parse_args()
 if args.check_only and args.serve_private:parser.error('Choose check-only or serve-private')
 for name,expected in json.loads((TRACE_CODE/'TRACE-SOURCE-PINS.json').read_text()).items():
  if sha(TRACE_CODE/name)!=expected:raise ValueError('Trace source pin mismatch: '+name)
 release=json.loads((TRACE_CODE/'release.json').read_text())
 if not args.serve_private:
  print(json.dumps(dict(status='PREPARED_FINAL_CHECK_ONLY',sources_verified=True,release=release,model_inference=False,server_started=False,public_changed=False),indent=2));return
 base=Path(args.base)
 if args.port is None or args.runtime is None:parser.error('Private serving requires explicit --port and --runtime')
 if args.port in (8130,8128) or not 1024<=args.port<=65535:parser.error('Port must be private and distinct from protected8130/8128')
 runtime=Path(args.runtime)
 if runtime.resolve()==(base/'runtime').resolve():parser.error('Private runtime must not be shared production runtime')
 cfg=json.loads((base/'config.json').read_text());cfg.update(release['serving']);cfg['host']='127.0.0.1';pins=json.loads((base/'SOURCE-PINS.json').read_text())
 for name,expected in pins.items():
  if sha(base/name)!=expected:raise ValueError('Production source pin mismatch: '+name)
 for path,expected in json.loads((base/'readonly-source-pins.json').read_text()).items():
  if sha(path)!=expected:raise ValueError('Original source pin mismatch: '+path)
 binding=json.loads((base/'binding.json').read_text())
 if binding['checkpoint_sha256']!=release['checkpoint_sha256']:raise ValueError('Checkpoint identity mismatch')
 for item in binding['files']:
  if sha(item['path'])!=item['sha256']:raise ValueError('Batch32 asset pin mismatch: '+item['role'])
 if args.port is not None:cfg['port']=args.port
 if args.runtime is not None:cfg['runtime']=args.runtime
 os.environ.update(HF_HOME=cfg['hf_home'],HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',NIGHT_SO_ONNX_THREADS='6',NIGHT_SO_ONNX_DIR=cfg['onnx_dir'])
 sys.path[:0]=[str(TRACE_CODE),str(base),cfg['ort_lib'],cfg['base_code']]
 from boost_runtime import read_boost,predict
 recipe=read_boost(cfg,binding)['policy']
 import torch
 torch.set_num_threads(2);torch.set_num_interop_threads(1)
 import onnx_so_pipeline
 started=time.perf_counter();engine=onnx_so_pipeline.Pipeline(Path(cfg['catalog']),Path(cfg['index_dir']),'cpu');load_ms=round(1000*(time.perf_counter()-started))
 catalog_version=json.loads(Path(cfg['catalog']).read_text())['version']
 options=engine.model.so_embedder.session.get_session_options()
 assert torch.get_num_threads()==2 and torch.get_num_interop_threads()==1 and options.intra_op_num_threads==6
 assert engine.model.so_embedder.session.get_providers()==['CPUExecutionProvider']
 hardware={'torch_threads':torch.get_num_threads(),'torch_interop_threads':torch.get_num_interop_threads(),'ORT_intra_threads':options.intra_op_num_threads,'ORT_inter_threads':options.inter_op_num_threads,'ORT_providers':engine.model.so_embedder.session.get_providers()}
 runtime=Path(cfg['runtime']);runtime.mkdir(exist_ok=True)
 from v7_trace import WorkflowPredictor
 tracer=WorkflowPredictor(base/'boost_runtime.py',base/'runtime/workflow-config.json',runtime/'workflow-traces',engine,recipe,
  dict(model_version=cfg['model_version'],index_version=cfg['serving_index_version'],catalog_version=catalog_version,
       serving_profile=cfg['serving_profile'],model_id=cfg['model_id'],checkpoint_sha256=binding['checkpoint_sha256'],
       assets=binding['files'],policy_name=recipe['name'],policy_sha256=binding['boost']['manifest_sha256'],
       policy_source_sha256=sha(base/'boost_policy.py'),catalog_sha256=sha(cfg['catalog']),
       source_pins_sha256=sha(base/'SOURCE-PINS.json'),hardware=hardware,
       siglip_preprocessing=engine.model.so_embedder.processor.image_processor.to_dict()),
  json.loads(Path(cfg['catalog']).read_text()),catalog_path=Path(cfg['catalog']))
 dispatcher=MainThreadDispatcher(max_pending=2)
 initialization_thread={'ident':threading.get_ident(),'native_id':threading.get_native_id(),'name':threading.current_thread().name}
 def execution_context():
  current={'ident':threading.get_ident(),'native_id':threading.get_native_id(),'name':threading.current_thread().name}
  actual=dict(hardware,torch_threads=torch.get_num_threads(),torch_interop_threads=torch.get_num_interop_threads())
  if current!=initialization_thread or actual['torch_threads']!=2 or actual['torch_interop_threads']!=1 or engine.model.so_embedder.session.get_session_options().intra_op_num_threads!=6 or engine.model.so_embedder.session.get_providers()!=['CPUExecutionProvider']:raise RuntimeError('Actual model owner thread/profile changed')
  return {'contract':'initialization_and_prediction_on_same_main_model_thread','initialization_thread':initialization_thread,'execution_thread':current,'execution_thread_matches_initialization':True,'hardware':actual}
 initial_context=execution_context()
 def predict_on_owner(content,request):
  request=dict(request,model_execution_context=execution_context())
  return tracer.predict(content,catalog_version,cfg['serving_index_version'],request)
 lock=threading.Lock();slots=threading.BoundedSemaphore(2)
 def metadata():return {'catalog_version':catalog_version,'index_version':cfg['serving_index_version'],'model_version':cfg['model_version'],'serving_profile':cfg['serving_profile']}
 class Handler(BaseHTTPRequestHandler):
  def reply(self,status,value):
   from workflow_trace import clean
   raw=json.dumps(clean(value),ensure_ascii=False,allow_nan=False).encode()
   try:
    self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));
    if getattr(self,'trace_id',None):self.send_header('X-Workflow-Trace-ID',self.trace_id)
    self.end_headers();self.wfile.write(raw)
   except (BrokenPipeError,ConnectionResetError):pass
  def do_GET(self):
   if urlsplit(self.path).path!='/healthz':return self.reply(404,{'error':'unknown route'})
   qualification=tracer.qualification_status()
   self.reply(200,dict(metadata(),status='stopping' if dispatcher.closed else 'ready',model_execution_context=initial_context,model_dispatch=dispatcher.health(),device='cpu',threads=2,ort_threads=6,cold_load_ms=load_ms,busy=lock.locked(),max_rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,policy=tracer.identity['policy_name'],workflow_trace=int(tracer.enabled()),trace_directory=str(tracer.directory),trace_schema='wine-workflow/1',qualification=qualification['status'],qualification_overlay=qualification,candidate_bundle_sha256=release['candidate_bundle_sha256']))
  def do_POST(self):
   self.trace_id=None;request_started=time.perf_counter()
   parsed=urlsplit(self.path)
   if parsed.path not in ['/predict','/v1/eval/predict']:return self.reply(404,{'error':'unknown route'})
   try:
    self.connection.settimeout(5)
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=30_000_000:raise ValueError('image body size')
    content=self.rfile.read(length);ctype=self.headers.get('Content-Type','')
    if len(content)!=length:raise ValueError('incomplete image body')
    if ctype.startswith('multipart/form-data'):
     msg=BytesParser(policy=mime_policy.default).parsebytes(b'Content-Type: '+ctype.encode()+b'\r\nMIME-Version: 1.0\r\n\r\n'+content)
     part=next((p for p in msg.iter_parts() if p.get_param('name',header='content-disposition')=='image'),None)
     if part is None:raise ValueError('missing image form field')
     content=part.get_payload(decode=True)
    track=parse_qs(parsed.query).get('track',['service'])[0]
    if track not in ['service','retrieval']:raise ValueError('track')
   except (ValueError,TypeError,KeyError,TimeoutError,OSError) as exc:
    error={'error':type(exc).__name__+': '+str(exc)[:200]};self.trace_id=tracer.rejection(error,request={'route':parsed.path});return self.reply(400,error)
   if not slots.acquire(blocking=False):
    self.trace_id=tracer.rejection({'error':'vision inference busy'},content,{'route':parsed.path,'admission':'slots full'});return self.reply(503,{'error':'vision inference busy'})
   acquired=False
   try:
    acquired=lock.acquire(timeout=3)
    if not acquired:
     self.trace_id=tracer.rejection({'error':'vision inference busy'},content,{'route':parsed.path,'admission':'lock timeout'});return self.reply(503,{'error':'vision inference busy'})
    request={'route':parsed.path,'track':track,'admission_ms':round(1000*(time.perf_counter()-request_started),3),'request_thread':{'ident':threading.get_ident(),'native_id':threading.get_native_id(),'name':threading.current_thread().name}}
    job=dispatcher.submit(lambda:predict_on_owner(content,request))
    result,self.trace_id=job.result();result.update(metadata());result['track']=track
    self.reply(200,result)
   except queue.Full:
    self.trace_id=tracer.rejection({'error':'vision inference busy'},content,{'route':parsed.path,'admission':'owner queue full'});self.reply(503,{'error':'vision inference busy'})
   except (ValueError,TypeError,KeyError,UnidentifiedImageError) as exc:
    self.trace_id=getattr(exc,'workflow_trace_id',None);self.reply(400,{'error':type(exc).__name__+': '+str(exc)[:200]})
   except Exception as exc:
    self.trace_id=getattr(exc,'workflow_trace_id',None);print(json.dumps({'inference_error':type(exc).__name__}),flush=True);self.reply(500,{'error':'vision inference failed'})
   finally:
    if acquired:lock.release()
    slots.release()
  def log_message(self,*args):pass
 server=ThreadingHTTPServer((cfg['host'],cfg['port']),Handler)
 server.daemon_threads=True
 http_thread=threading.Thread(target=server.serve_forever,name='c09-http-admission',daemon=True)
 proof=dict(metadata(),pid=os.getpid(),cold_load_ms=load_ms,hardware=hardware,source_pins_sha256=sha(base/'SOURCE-PINS.json'),host=cfg['host'],port=cfg['port'],model_execution_context=initial_context,model_dispatch=dispatcher.health())
 def stop(signum,frame):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop)
 http_started=False
 try:
  http_thread.start();http_started=True
  (runtime/'READY.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)
  dispatcher.run()
 except KeyboardInterrupt:pass
 finally:
  # Wake pending request futures before HTTP shutdown; model/OCR close stays
  # on the same owner thread. Only this server/queue/model are controlled.
  dispatcher.close()
  if http_started:server.shutdown();http_thread.join(timeout=2)
  server.server_close();tracer.close()
if __name__=='__main__':main()
