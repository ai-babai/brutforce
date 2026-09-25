"""Single-process, warmed local HTTP endpoint for live end-to-end timing.

POST /v1/eval/predict?track=service|retrieval accepts raw image bytes or
multipart form field "image". No hosted inference calls occur per request.
"""
import argparse,hashlib,io,json,time
from email.parser import BytesParser
from email import policy
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import numpy as np
from PIL import Image,ImageOps
from model import Vision
from label_context_v2 import context_box, VERSION as LABEL_CONTEXT_VERSION
from ranking import Lexical,top
from fuse import rank_fuse,ocr_top,VARIANTS

class Pipeline:
 def __init__(self,catalog_path,index_dir,device='cuda',ocr_threads=2,label_context=False):
  from paddleocr import PaddleOCR
  t=time.perf_counter();catalog=json.loads(Path(catalog_path).read_text())['references']
  self.slugs=[r['slug'] for r in catalog]
  self.lexical=Lexical([{'slug':r['slug'],'title':r.get('title',''),'producer':r.get('winery','')} for r in catalog])
  index=np.load(Path(index_dir)/'index.npz')
  index_info=json.loads((Path(index_dir)/'index-info.json').read_text())
  if (index_info['label_crop']==LABEL_CONTEXT_VERSION)!=label_context:
   raise ValueError('label crop mode does not match index; use --label-context for v2')
  self.label_context=label_context
  if list(index['slugs'])!=self.slugs:raise ValueError('catalog/index slug order mismatch')
  self.full=index['full'];self.label=index['label']
  self.model=Vision(device)
  self.device=self.model.device
  self.gpu_name=(self.model.torch.cuda.get_device_name(0)
                 if self.device.startswith('cuda') else None)
  self.ocr=PaddleOCR(device='cpu',cpu_threads=ocr_threads,enable_mkldnn=False,
      text_detection_model_name='PP-OCRv5_mobile_det',
      text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',
      text_det_limit_side_len=1280,text_det_limit_type='max',
      use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
  self.load_ms=round((time.perf_counter()-t)*1000)

 def predict(self,content,track):
  if track not in ('service','retrieval'):raise ValueError('track')
  start=time.perf_counter();stage={}
  with Image.open(io.BytesIO(content)) as im:image=ImageOps.exif_transpose(im).convert('RGB')
  stage['decode_ms']=round((time.perf_counter()-start)*1000)
  if track=='service':
   target,selection=self.model.select_service(image)
   stage['detect_ms']=selection['detect_ms'];stage['class_ms']=selection['class_ms']
   standalone=None;rescue=None
   if target is None and selection['selection_reason']=='no_bottle_detected':
    region,standalone=self.model.label_region(image)
    if standalone['source'].startswith(('owlv2','yoloe26s')) and standalone['score']>=.15:
     target=region;selection['selected_box']=standalone['box']
     selection['selection_reason']='standalone_label_no_bottle'
   elif target is None and selection['selection_reason']=='detected_bottles_classified_nonwine' and hasattr(self,'rescue_rejected'):
    target,rescue=self.rescue_rejected(image,selection)
    if target is not None:
     selection['selected_box']=rescue['selected_box']
     selection['selection_reason']='independent_label_ocr_rescue'
  else:
   target=image;selection={'boxes':[],'selected_box':[0,0,*image.size],
                           'selection_reason':'verified_retrieval_crop'}
   stage['detect_ms']=0;stage['class_ms']=0;standalone=None;rescue=None
  whole=[];label=[];ocr_rank=[];raw_text='';ocr_error=None;label_choice=None;label_context_box=None
  stage.update(label_detect_ms=0,whole_embedding_ms=0,label_embedding_ms=0,ocr_ms=0,rank_ms=0)
  if target is None and standalone:stage['label_detect_ms']=standalone['detect_ms']
  if target is not None:
   if standalone:region=target;label_choice=standalone
   else:region,label_choice=self.model.label_region(target)
   stage['label_detect_ms']=label_choice['detect_ms']
   if self.label_context:
    detected=None if standalone else label_choice['box']
    label_context_box=context_box(target.size,detected)
    region=target.crop(label_context_box)
   t=time.perf_counter();whole_feature=self.model.image_features([target])[0]
   stage['whole_embedding_ms']=round((time.perf_counter()-t)*1000)
   t=time.perf_counter();label_feature=self.model.image_features([region])[0]
   stage['label_embedding_ms']=round((time.perf_counter()-t)*1000)
   t=time.perf_counter()
   whole_scores=np.where(np.isfinite(self.full).all(axis=1),self.full@whole_feature,np.nan)
   label_scores=np.where(np.isfinite(self.label).all(axis=1),self.label@label_feature,np.nan)
   whole=top(whole_scores,self.slugs);label=top(label_scores,self.slugs)
   stage['rank_ms']=round((time.perf_counter()-t)*1000)
   if rescue is not None and rescue.get('ocr_text') is not None:
    raw_text=rescue['ocr_text'];ocr_rank=ocr_top(self.lexical,raw_text,self.slugs)
    stage['ocr_ms']=rescue['ocr_ms']
   else:
    t=time.perf_counter()
    try:
     # Match offline OCR's JPEG-92 target bytes before BGR decoding.
     buf=io.BytesIO();target.save(buf,'JPEG',quality=92)
     with Image.open(io.BytesIO(buf.getvalue())) as encoded:
      ocr_image=np.asarray(encoded.convert('RGB'))[:,:,::-1].copy()
     result=list(self.ocr.predict(ocr_image))
     res=result[0].json['res'] if result else {}
     raw_text='\n'.join(str(v) for v,s in zip(res.get('rec_texts',[]),res.get('rec_scores',[])) if float(s)>=.35)
     ocr_rank=ocr_top(self.lexical,raw_text,self.slugs)
    except Exception as e:ocr_error=type(e).__name__+': '+str(e)[:250]
    stage['ocr_ms']=round((time.perf_counter()-t)*1000)
  t=time.perf_counter()
  branches={'whole':whole,'label':label,'ocr':ocr_rank}
  variants={name:rank_fuse({key:branches[key] for key in subset}) for name,subset in VARIANTS.items()}
  fused=variants['all']
  if track=='service':
   prediction={'action':'no_match'} if target is None else {'slug':fused[0]['slug']} if fused else {'action':'insufficient_information'}
  else:
   prediction={'ranked_slugs':[v['slug'] for v in fused]}
  stage['fusion_ms']=round((time.perf_counter()-t)*1000)
  stage['total_ms']=round((time.perf_counter()-start)*1000)
  result={**prediction,'track':track,'timings_ms':stage,'selection':selection,
          'label_selection':label_choice,'label_context_box':label_context_box,
          'label_crop_mode':LABEL_CONTEXT_VERSION if self.label_context else 'v1-detected-box',
          'branches_top20':branches,'variants_top20':variants,
          'ocr_text':raw_text,'ocr_error':ocr_error,'rescue':rescue,
          'image_sha256':hashlib.sha256(content).hexdigest()}
  return result

class Handler(BaseHTTPRequestHandler):
 pipeline=None
 def do_GET(self):
  if self.path!='/healthz':self.send_error(404);return
  self.respond(200,{'status':'ready','cold_load_ms':self.pipeline.load_ms,
                    'device':self.pipeline.device,'gpu_name':self.pipeline.gpu_name,
                    'label_crop_mode':LABEL_CONTEXT_VERSION if self.pipeline.label_context else 'v1-detected-box'})
 def do_POST(self):
  parsed=urlsplit(self.path)
  if parsed.path not in ('/predict','/v1/eval/predict'):self.send_error(404);return
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length<=0 or length>30_000_000:raise ValueError('image body size')
   body=self.rfile.read(length);ctype=self.headers.get('Content-Type','')
   if ctype.startswith('multipart/form-data'):
    mime=b'Content-Type: '+ctype.encode()+b'\r\nMIME-Version: 1.0\r\n\r\n'+body
    message=BytesParser(policy=policy.default).parsebytes(mime)
    image_part=next((p for p in message.iter_parts() if p.get_param('name',header='content-disposition')=='image'),None)
    if image_part is None:raise ValueError('missing image form field')
    content=image_part.get_payload(decode=True)
   else:content=body
   track=parse_qs(parsed.query).get('track',['service'])[0]
   result=self.pipeline.predict(content,track)
   self.respond(200,result)
  except Exception as e:
   self.respond(400,{'error':type(e).__name__+': '+str(e)[:300]})
 def respond(self,status,obj):
  data=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
  self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,fmt,*args):
  print('%s %s'%(self.address_string(),fmt%args),flush=True)

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--catalog',type=Path,required=True);p.add_argument('--index-dir',type=Path,required=True)
 p.add_argument('--device',default='cuda');p.add_argument('--ocr-threads',type=int,default=2)
 p.add_argument('--label-context',action='store_true',help='use v2 context crop and matching v2 index')
 p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8080)
 a=p.parse_args();pipeline=Pipeline(a.catalog,a.index_dir,a.device,a.ocr_threads,a.label_context)
 Handler.pipeline=pipeline
 print(json.dumps({'ready':True,'cold_load_ms':pipeline.load_ms,'device':pipeline.device,
                   'gpu_name':pipeline.gpu_name,'host':a.host,'port':a.port}),flush=True)
 HTTPServer((a.host,a.port),Handler).serve_forever()
if __name__=='__main__':main()
