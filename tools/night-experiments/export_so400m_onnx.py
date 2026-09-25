"""Export visual-only SO400M FP32; validate pixels, vectors, and exact-index ranks.

No labels or scoring answers are inputs. An export is usable only after parity.
"""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

MODEL='google/siglip2-so400m-patch16-384'
REV='dd658faac399427308559e2c3ac1e99cbe43845d'

class Visual(torch.nn.Module):
    def __init__(self, vision):
        super().__init__();self.vision=vision
    def forward(self,pixel_values):
        value=self.vision(pixel_values=pixel_values,return_dict=False)[1]
        return torch.nn.functional.normalize(value.float(),dim=-1)

def main():
    p=argparse.ArgumentParser();p.add_argument('--images',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=16)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(4);torch.backends.mha.set_fastpath_enabled(False)
    processor=AutoProcessor.from_pretrained(MODEL,revision=REV)
    model=AutoModel.from_pretrained(MODEL,revision=REV,attn_implementation='eager',use_safetensors=True).eval()
    visual=Visual(model.vision_model).eval();del model
    processor.save_pretrained(a.out/'processor')
    files=sorted(p for p in a.images.rglob('*') if p.suffix.lower() in ('.png','.jpg','.jpeg'))[:a.count]
    assert len(files)==a.count
    pixels=[processor(images=Image.open(f).convert('RGB'),return_tensors='pt')['pixel_values'] for f in files]
    with torch.inference_mode():
        expected=[visual(x).numpy() for x in pixels]
    path=a.out/'vision.onnx'
    if not path.exists():
        torch.onnx.export(visual,(pixels[0],),str(path),input_names=['pixel_values'],output_names=['embedding'],opset_version=17,dynamo=False,external_data=True)
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    comparisons=[]
    for f,x,y in zip(files,pixels,expected):
        t=time.perf_counter();z=session.run(None,{'pixel_values':x.numpy()})[0];ms=(time.perf_counter()-t)*1000
        comparisons.append({'image':f.name,'image_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'max_abs':float(np.max(np.abs(y-z))),'cosine':float(np.sum(y*z)),'ort_cpu_ms':ms})
    receipt={'model':MODEL,'revision':REV,'dtype':'float32','opset':17,'input_shape':list(pixels[0].shape),'threads':4,'scope':'encoder only; pod CPU; no end-to-end claim','comparisons':comparisons,'versions':{'torch':torch.__version__,'onnxruntime':ort.__version__},'files':{str(f.relative_to(a.out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.rglob('*') if f.is_file()}}
    receipt['parity_pass']=all(r['max_abs']<1e-4 and r['cosine']>.99999 for r in comparisons)
    (a.out/'parity.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    assert receipt['parity_pass'],'Export parity failed'

if __name__=='__main__':main()
