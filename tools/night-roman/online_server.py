"""Fresh local HTTP B→Roman-20 cascade; also returns Roman-5 from group zero.

No saved B predictions or answers are read. B runs as its own warmed HTTP
service. This Qwen server uses the pinned Roman adapter and runtime-linear
vision patch policy recorded in the offline experiment.
"""
import argparse
import hashlib
import io
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from peft import PeftModel
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3_5ForConditionalGeneration

from run import ADAPTER_SHA, BASE_SHARDS, PROMPT, load_reference, read_rows, rerank, sha, task


def query_image(content):
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > 80_000_000:
            raise ValueError('Query pixel bound exceeded')
        if source.format == 'JPEG' and source.width * source.height > 40_000_000:
            source.draft('RGB',(1800,1800))
        rgba = ImageOps.exif_transpose(source).convert('RGBA')
    canvas = Image.new('RGBA',rgba.size,'white')
    canvas.alpha_composite(rgba)
    image = canvas.convert('RGB')
    image.thumbnail((1800,1800),Image.Resampling.LANCZOS)
    rgba.close();canvas.close()
    return image


class Cascade:
    def __init__(self, root, b_url, cache_refs=False, b_skip_threshold_ms=0):
        self.root = root.resolve()
        self.b_url = b_url
        self.b_skip_threshold_ms = b_skip_threshold_ms
        inp = self.root/'online-input-v1'
        provenance = json.loads((inp/'provenance.json').read_text())
        for name,expected in provenance['files'].items():
            if sha(inp/name) != expected:
                raise ValueError('Online input changed: '+name)
        self.refs = {r['slug']:r for r in read_rows(inp/'references.jsonl')}
        self.cards = {r['slug']:r for r in read_rows(inp/'cards.jsonl')}
        if len(self.refs)!=2103 or len(self.cards)!=2103:
            raise ValueError('Catalog cardinality mismatch')
        self.reference_cache = None
        if cache_refs:
            # Public, immutable gate-v2 bytes. Verify each SHA once at startup
            # and keep exactly the same transformed image for future calls.
            self.reference_cache = {}
            for digest in sorted({r['sha256'] for r in self.refs.values() if r['sha256']}):
                self.reference_cache[digest] = load_reference(self.root/'refs'/(digest+'.webp'),digest)
            print(f'preloaded exact reference images: {len(self.reference_cache)}',flush=True)
        if sha(self.root/'adapter/adapter_model.safetensors') != ADAPTER_SHA:
            raise ValueError('Adapter SHA mismatch')
        if {p.name:sha(p) for p in (self.root/'base').glob('*.safetensors')} != BASE_SHARDS:
            raise ValueError('Base SHA mismatch')
        torch.set_num_threads(6)
        self.processor = AutoProcessor.from_pretrained(self.root/'base',min_pixels=65536,
            max_pixels=524288,trust_remote_code=False)
        ids=[self.processor.tokenizer.encode(str(i),add_special_tokens=False) for i in range(6)]
        if any(len(x)!=1 for x in ids):
            raise ValueError('Digit tokenization changed')
        self.digits=torch.tensor([x[0] for x in ids],device='cuda')
        model=Qwen3_5ForConditionalGeneration.from_pretrained(self.root/'base',
            quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
                bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_skip_modules=['visual','lm_head']),device_map={'':'cuda:0'},
            dtype=torch.bfloat16,attn_implementation='sdpa',trust_remote_code=False)
        self.model=PeftModel.from_pretrained(model,str(self.root/'adapter'),is_trainable=False).eval()
        patch=self.model.get_base_model().model.visual.patch_embed
        conv=patch.proj
        if tuple(conv.kernel_size)!=tuple(conv.stride) or tuple(conv.padding)!=(0,0,0) or conv.groups!=1:
            raise ValueError('Vision patch geometry changed')
        def linear_patch(hidden_states):
            patches=hidden_states.view(-1,patch.in_channels,patch.temporal_patch_size,
                patch.patch_size,patch.patch_size).to(dtype=conv.weight.dtype)
            return F.linear(patches.flatten(1),conv.weight.flatten(1),conv.bias)
        patch.forward=linear_patch
        self.records=self.root/'online-server-records.jsonl'

    def forward(self, query, slugs, key):
        ordered,payload=task(key,slugs,self.cards)
        refs=[]
        try:
            for slug in ordered:
                digest=self.refs[slug]['sha256']
                if not digest:
                    raise FileNotFoundError('Excluded exact reference '+slug)
                refs.append(self.reference_cache[digest] if self.reference_cache is not None else
                    load_reference(self.root/'refs'/(digest+'.webp'),digest))
            content=[dict(type='text',text=PROMPT),dict(type='image')]
            for card in payload:
                content.extend([dict(type='text',text=json.dumps(card,ensure_ascii=False)),dict(type='image')])
            chat=self.processor.apply_chat_template([dict(role='user',content=content)],
                tokenize=False,add_generation_prompt=True,enable_thinking=False)
            t0=time.perf_counter()
            tensors=self.processor(text=[chat],images=[query,*refs],return_tensors='pt').to('cuda')
            with torch.inference_mode():
                logits=self.model(**tensors,use_cache=False,logits_to_keep=1).logits[0,-1,self.digits].float()
                probs=torch.softmax(logits,dim=-1).cpu().tolist()
            torch.cuda.synchronize()
            winner=max(range(6),key=lambda i:probs[i])
            return dict(candidate_slugs=ordered,probabilities=probs,
                winner=ordered[winner] if winner<5 else None,
                processor_model_ms=round((time.perf_counter()-t0)*1000,3))
        finally:
            if self.reference_cache is None:
                for image in refs:
                    image.close()

    def predict(self, content, track, case_id, mode='twenty'):
        if track not in ('service','retrieval'):
            raise ValueError('track must be service or retrieval')
        if mode not in ('five','twenty'):
            raise ValueError('mode must be five or twenty')
        started=time.perf_counter()
        digest=hashlib.sha256(content).hexdigest()
        b_req=Request(self.b_url+'?track='+track,data=content,method='POST',
            headers={'Content-Type':'image/jpeg'})
        with urlopen(b_req,timeout=30) as response:
            b_status=response.status
            b=json.load(response)
        b_elapsed=round((time.perf_counter()-started)*1000,3)
        if b_status!=200 or b.get('image_sha256')!=digest:
            raise ValueError('Fresh B HTTP failure or image SHA mismatch')
        scored=b.get('variants_top20',{}).get('all') or []
        ranked=[x['slug'] for x in scored]
        if len(ranked) not in (0,20) or len(ranked)!=len(set(ranked)):
            raise ValueError('Fresh B candidate pool malformed')
        if any(slug not in self.refs for slug in ranked):
            raise ValueError('Fresh B slug outside public catalog')
        row=dict(ranked_slugs=ranked,ranked_scores=[x['score'] for x in scored])
        result=dict(case_id=case_id,track=track,mode=mode,query_sha256=digest,b_http_status=b_status,
            b_http_ms=b_elapsed,b_action=b.get('action'),b_slug=b.get('slug'),
            b_ranked=ranked,b_ranked_scores=row['ranked_scores'],
            b_model_version=b.get('model_version'),b_ocr_error=b.get('ocr_error'),
            b_timings_ms=b.get('timings_ms'), b_ocr_text=b.get('ocr_text'),
            b_selection_reason=(b.get('selection') or {}).get('selection_reason'),
            b_selected_box=(b.get('selection') or {}).get('selected_box'),
            b_label_box=(b.get('label_selection') or {}).get('box'))
        unavailable=[s for s in ranked if not self.refs[s]['sha256'] or
            not (self.root/'refs'/(self.refs[s]['sha256']+'.webp')).is_file()]
        result['missing_references']=unavailable
        roman_start=time.perf_counter()
        if not ranked:
            result['roman5_ranked']=ranked
            result['roman20_ranked']=ranked
            result['status']='upstream_no_candidates'
        elif self.b_skip_threshold_ms and b_elapsed >= self.b_skip_threshold_ms:
            result['roman5_ranked']=ranked
            result['roman20_ranked']=ranked
            result['status']='deadline_b_fallback'
            result['deadline_b_skip_threshold_ms']=self.b_skip_threshold_ms
        else:
            query=query_image(content)
            try:
                if not any(s in unavailable for s in ranked[:5]):
                    first=self.forward(query,ranked[:5],digest)
                    result['adapter5']=first
                    result['roman5_ranked']=rerank(row,first['candidate_slugs'],first['probabilities'],.7,.025)
                else:
                    result['roman5_ranked']=ranked
                if mode=='five':
                    result['status']='complete_five' if not any(s in unavailable for s in ranked[:5]) else 'missing_references'
                elif not unavailable:
                    groups=[first]
                    for offset in (5,10,15):
                        groups.append(self.forward(query,ranked[offset:offset+5],digest))
                    winners=[g['winner'] for g in groups if g['winner']]
                    selected=[]
                    for slug in [*winners,ranked[0],*ranked[:5]]:
                        if slug not in selected:
                            selected.append(slug)
                        if len(selected)==5:
                            break
                    if set(selected)==set(ranked[:5]):
                        final=first;reused=True
                    else:
                        final=self.forward(query,selected,digest);reused=False
                    result['groups20']=groups
                    result['final20']=final
                    result['final20_reused']=reused
                    result['roman20_ranked']=rerank(row,final['candidate_slugs'],final['probabilities'],.9,.4)
                else:
                    result['roman20_ranked']=ranked
                if mode=='twenty':
                    result['status']='complete' if not unavailable else 'missing_references'
            finally:
                query.close()
        result['roman_wall_ms']=round((time.perf_counter()-roman_start)*1000,3)
        result['total_server_ms']=round((time.perf_counter()-started)*1000,3)
        with self.records.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(result,ensure_ascii=False)+'\n')
            stream.flush()
        print(f'{case_id} {track} {result["status"]} b={b_elapsed} roman={result["roman_wall_ms"]} total={result["total_server_ms"]}',flush=True)
        return result


class Handler(BaseHTTPRequestHandler):
    cascade=None
    def do_GET(self):
        if self.path!='/healthz':
            self.send_error(404);return
        self.respond(200,dict(status='ready',model='Roman20-runtime-linear',
            b_url=self.cascade.b_url,gpu=torch.cuda.get_device_name(),
            b_skip_threshold_ms=self.cascade.b_skip_threshold_ms,
            reference_cache=self.cascade.reference_cache is not None))
    def do_POST(self):
        parsed=urlsplit(self.path)
        if parsed.path!='/v1/eval/predict':
            self.send_error(404);return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>30_000_000:
                raise ValueError('Image body size')
            content=self.rfile.read(n)
            track=parse_qs(parsed.query).get('track',['service'])[0]
            mode=parse_qs(parsed.query).get('mode',['twenty'])[0]
            case_id=self.headers.get('X-Case-ID','')
            result=self.cascade.predict(content,track,case_id,mode)
            self.respond(200,result)
        except Exception as error:
            print('request error '+type(error).__name__+': '+str(error)[:300],flush=True)
            self.respond(500,dict(error=type(error).__name__+': '+str(error)[:300]))
    def respond(self,status,result):
        data=json.dumps(result,ensure_ascii=False).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError:
            print('client timed out before response',flush=True)
    def log_message(self,fmt,*args):
        print('%s %s'%(self.address_string(),fmt%args),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--b-url',default='http://127.0.0.1:8091/v1/eval/predict')
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8092)
    p.add_argument('--cache-refs',action='store_true')
    p.add_argument('--b-skip-threshold-ms',type=int,default=0)
    a=p.parse_args()
    if a.b_skip_threshold_ms < 0:
        raise ValueError('B skip threshold must be nonnegative')
    Handler.cascade=Cascade(a.root,a.b_url,a.cache_refs,a.b_skip_threshold_ms)
    print(json.dumps(dict(ready=True,model='Roman20-runtime-linear',b_url=a.b_url,
        gpu=torch.cuda.get_device_name())),flush=True)
    HTTPServer((a.host,a.port),Handler).serve_forever()


if __name__=='__main__':
    main()
