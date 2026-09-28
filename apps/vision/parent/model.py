"""Downloadable-only bottle selection and independent visual embeddings.

No target labels, gold, or API keys enter this process. Model weights are pinned.
"""
from __future__ import annotations
import hashlib
import math
import time
from pathlib import Path
from PIL import Image, ImageOps

OWL_ID = 'google/owlv2-base-patch16-ensemble'
OWL_REV = 'cfd3195ba4ea9592eec887ded089f4c08eff231d'
SIGLIP_ID = 'google/siglip2-base-patch16-224'
SIGLIP_REV = '75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2'
DETECT_PROMPTS = [
    'a wine bottle', 'a glass bottle of wine', 'a beer bottle',
    'a bottle of liquor', 'a milk bottle', 'a carton of milk',
    'a product bottle',
]
LABEL_PROMPTS = ['a wine label on a bottle', 'a rectangular product label with wine text',
                 'a printed wine bottle label']
CLASS_PROMPTS = [
    'a bottle of wine with a wine label', 'a beer bottle',
    'a bottle of milk', 'a bottle of spirits', 'a soft drink bottle',
]

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_image(path, expected_hash=None):
    path = Path(path)
    if expected_hash and sha256(path) != expected_hash:
        raise ValueError(f'image hash mismatch: {path}')
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert('RGB')

def clamp_box(box, size):
    w, h = size
    x1,y1,x2,y2 = box
    x1=max(0,min(w-1,math.floor(x1)));y1=max(0,min(h-1,math.floor(y1)))
    x2=max(x1+1,min(w,math.ceil(x2)));y2=max(y1+1,min(h,math.ceil(y2)))
    return [x1,y1,x2,y2]

def label_band(bottle):
    """Declared heuristic, not a learned label detector. Preserve partial crops."""
    w,h=bottle.size
    return bottle.crop(clamp_box((w*.06,h*.30,w*.94,h*.84),(w,h)))

def iou(a,b):
    x1=max(a[0],b[0]); y1=max(a[1],b[1]); x2=min(a[2],b[2]); y2=min(a[3],b[3])
    inter=max(0,x2-x1)*max(0,y2-y1)
    aa=max(1,(a[2]-a[0])*(a[3]-a[1]));bb=max(1,(b[2]-b[0])*(b[3]-b[1]))
    return inter/(aa+bb-inter)

class Vision:
    def __init__(self, device='cuda'):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection, AutoModel
        self.torch=torch
        self.device=device if device!='cuda' or torch.cuda.is_available() else 'cpu'
        self.detector_processor=AutoProcessor.from_pretrained(OWL_ID, revision=OWL_REV)
        self.detector=AutoModelForZeroShotObjectDetection.from_pretrained(OWL_ID, revision=OWL_REV, use_safetensors=True).to(self.device).eval()
        self.embed_processor=AutoProcessor.from_pretrained(SIGLIP_ID, revision=SIGLIP_REV)
        self.embedder=AutoModel.from_pretrained(SIGLIP_ID, revision=SIGLIP_REV, use_safetensors=True).to(self.device).eval()
        self.class_features=self.text_features(CLASS_PROMPTS)

    def _sync(self):
        if self.device.startswith('cuda'):self.torch.cuda.synchronize()

    def image_features(self, images, batch_size=24):
        import torch.nn.functional as F
        if not images:return []
        all_features=[]
        for start in range(0,len(images),batch_size):
            batch=images[start:start+batch_size]
            inp=self.embed_processor(images=batch,return_tensors='pt').to(self.device)
            with self.torch.inference_mode():
                v=self.embedder.get_image_features(**inp)
                if not isinstance(v,self.torch.Tensor):v=v.pooler_output
                v=F.normalize(v.float(),dim=-1)
            all_features.append(v.cpu())
        self._sync()
        return self.torch.cat(all_features).numpy()

    def text_features(self, texts):
        import torch.nn.functional as F
        inp=self.embed_processor(text=texts,padding='max_length',return_tensors='pt').to(self.device)
        with self.torch.inference_mode():
            v=self.embedder.get_text_features(**inp)
            if not isinstance(v,self.torch.Tensor):v=v.pooler_output
            v=F.normalize(v.float(),dim=-1)
        return v.cpu().numpy()

    def _detect_prompts(self, image, prompts, threshold):
        t=time.perf_counter()
        # OWLv2 runs at a fixed internal resolution; reduce source pixels before
        # SciPy preprocessing, then return boxes in original-image coordinates.
        detector_image=image.copy();detector_image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
        sx=image.width/detector_image.width;sy=image.height/detector_image.height
        inp=self.detector_processor(text=[prompts],images=detector_image,return_tensors='pt').to(self.device)
        with self.torch.inference_mode():out=self.detector(**inp)
        self._sync()
        res=self.detector_processor.post_process_object_detection(out,target_sizes=self.torch.tensor([detector_image.size[::-1]]),threshold=threshold)[0]
        raw=[]
        for box,score,label in zip(res['boxes'],res['scores'],res['labels']):
            idx=int(label);coords=box.tolist();b=clamp_box([coords[0]*sx,coords[1]*sy,coords[2]*sx,coords[3]*sy],image.size)
            raw.append({'box':b,'score':float(score),'prompt':prompts[idx]})
        raw.sort(key=lambda x:x['score'],reverse=True)
        distinct=[]
        for item in raw:
            if all(iou(item['box'],prior['box'])<.65 for prior in distinct):distinct.append(item)
        return distinct[:12],round((time.perf_counter()-t)*1000)

    def detect(self, image, threshold=.08):
        return self._detect_prompts(image,DETECT_PROMPTS,threshold)

    def label_region(self, image):
        candidates,ms=self._detect_prompts(image,LABEL_PROMPTS,.06)
        w,h=image.size
        eligible=[];large=[]
        for x in candidates:
            box=x['box'];area=(box[2]-box[0])*(box[3]-box[1])/(w*h)
            if area<.008:continue
            cx=(box[0]+box[2])/(2*w);cy=(box[1]+box[3])/(2*h)
            key=(math.hypot(cx-.5,cy-.62)-.35*x['score'],x)
            if area<=.65:eligible.append(key)
            else:large.append(key)
        if eligible:
            selected=min(eligible,key=lambda v:v[0])[1]
            return image.crop(selected['box']),{'source':'owlv2_label','box':selected['box'],'score':selected['score'],
                                                'detect_ms':ms,'candidates':candidates}
        if large and h/w<=2.2:
            selected=min(large,key=lambda v:v[0])[1]
            return image.crop(selected['box']),{'source':'owlv2_label_closeup','box':selected['box'],
                                                'score':selected['score'],'detect_ms':ms,'candidates':candidates}
        fallback=clamp_box((w*.06,h*.30,w*.94,h*.84),image.size)
        return image.crop(fallback),{'source':'heuristic_band_fallback','box':fallback,'score':None,
                                     'detect_ms':ms,'candidates':candidates}

    def select_service(self,image):
        started=time.perf_counter()
        candidates,detect_ms=self.detect(image)
        if not candidates:
            return None,{'boxes':[],'selected_box':None,'selection_reason':'no_bottle_detected','detect_ms':detect_ms,'class_ms':0}
        crops=[image.crop(x['box']) for x in candidates]
        features=self.image_features(crops)
        semantic=features@self.class_features.T
        w,h=image.size
        for cand,sim in zip(candidates,semantic):
            cand['wine_margin']=round(float(sim[0]-max(sim[1:])),5)
            cx=(cand['box'][0]+cand['box'][2])/(2*w);cy=(cand['box'][1]+cand['box'][3])/(2*h)
            cand['center_distance']=round(math.hypot(cx-.5,cy-.5),5)
        wine=[c for c in candidates if c['wine_margin']>=-.015 or c['prompt'] in DETECT_PROMPTS[:2]]
        if not wine:
            return None,{'boxes':candidates,'selected_box':None,'selection_reason':'detected_bottles_classified_nonwine','detect_ms':detect_ms,'class_ms':round((time.perf_counter()-started)*1000)-detect_ms}
        chosen=min(wine,key=lambda c:(c['center_distance'],-c['wine_margin']))
        return image.crop(chosen['box']),{'boxes':candidates,'selected_box':chosen['box'],'selection_reason':'nearest_center_wine','detect_ms':detect_ms,'class_ms':round((time.perf_counter()-started)*1000)-detect_ms}
