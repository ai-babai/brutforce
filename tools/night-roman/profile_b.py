"""Gold-blind B stage profiler; instruments a fresh isolated B Pipeline."""
import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path


class TimedCallable:
    def __init__(self, fn, label, measurements, synchronize=None):
        self.fn=fn;self.label=label;self.measurements=measurements;self.synchronize=synchronize
    def __call__(self,*args,**kwargs):
        if self.synchronize: self.synchronize()
        t=time.perf_counter()
        result=self.fn(*args,**kwargs)
        if self.synchronize: self.synchronize()
        self.measurements[self.label].append(round((time.perf_counter()-t)*1000,3))
        return result
    def __getattr__(self,name):
        return getattr(self.fn,name)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--b-source',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--ocr-threads',type=int,default=2)
    p.add_argument('--mkldnn',action='store_true')
    p.add_argument('--ocr-max-side',type=int,default=0)
    p.add_argument('--case-ids',default='organizer-real-042,organizer-real-043,organizer-real-044,organizer-real-045,organizer-real-046')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(a.b_source))
    import server, softgate_server
    from detector_encoder_server import RTSoVision
    if a.mkldnn:
        import paddleocr
        original_ocr=paddleocr.PaddleOCR
        def mkldnn_ocr(*args,**kwargs):
            if kwargs.get('enable_mkldnn') is not False:
                raise ValueError('Unexpected Paddle MKLDNN baseline')
            kwargs['enable_mkldnn']=True
            return original_ocr(*args,**kwargs)
        paddleocr.PaddleOCR=mkldnn_ocr
    server.Vision=RTSoVision
    pipeline=softgate_server.Pipeline(a.catalog,a.index,'cuda',a.ocr_threads)
    if a.ocr_max_side:
        import cv2
        original_predict=pipeline.ocr.predict
        def resized_predict(image):
            height,width=image.shape[:2]
            longest=max(height,width)
            if longest>a.ocr_max_side:
                scale=a.ocr_max_side/longest
                image=cv2.resize(image,(max(1,round(width*scale)),max(1,round(height*scale))),
                    interpolation=cv2.INTER_AREA)
            return original_predict(image)
        pipeline.ocr.predict=resized_predict
    vision=pipeline.model
    devices={name:str(next(model.parameters()).device) for name,model in {
        'rtdetr':vision.rtdetr,'owlv2':vision.detector,'base224':vision.embedder,
        'so400m384':vision.so_embedder.model}.items()}
    assert all(device.startswith('cuda') for device in devices.values()), devices
    measurements=collections.defaultdict(list)
    vision.embed_processor=TimedCallable(vision.embed_processor,'base224_processor_ms',measurements)
    vision.embedder.get_image_features=TimedCallable(vision.embedder.get_image_features,
        'base224_forward_ms',measurements,vision._sync)
    vision.so_embedder.processor=TimedCallable(vision.so_embedder.processor,
        'so400m_processor_ms',measurements)
    vision.so_embedder.model.get_image_features=TimedCallable(
        vision.so_embedder.model.get_image_features,'so400m_forward_ms',measurements,vision._sync)
    vision.detector_processor=TimedCallable(vision.detector_processor,'owlv2_processor_ms',measurements)
    vision.detector.forward=TimedCallable(vision.detector.forward,'owlv2_forward_ms',measurements,vision._sync)
    vision.rtdetr_processor=TimedCallable(vision.rtdetr_processor,'rtdetr_processor_ms',measurements)
    vision.rtdetr.forward=TimedCallable(vision.rtdetr.forward,'rtdetr_forward_ms',measurements,vision._sync)
    requests={r['case_id']:r for r in (json.loads(s) for s in
        (a.root/'online-input-v1/requests.jsonl').read_text().splitlines())}
    saved={r['case_id']:r for r in (json.loads(s) for s in
        (a.root/'input-v1/requests.jsonl').read_text().splitlines())}
    prefix=Path('/Users/skif/ml-data/brutforce/integration-20260925-1700/model/input-stage')
    output=[]
    for case_id in a.case_ids.split(','):
        case=requests[case_id]
        path=a.root/'input-stage'/Path(case['query_path']).relative_to(prefix)
        content=path.read_bytes()
        assert hashlib.sha256(content).hexdigest()==case['query_sha256']
        measurements.clear()
        t=time.perf_counter()
        result=pipeline.predict(content,case['track'])
        elapsed=round((time.perf_counter()-t)*1000,3)
        ranks=[x['slug'] for x in result['variants_top20']['all']]
        original=saved[case_id]
        output.append({'case_id':case_id,'track':case['track'],'elapsed_ms':elapsed,
            'same_rank':ranks==original['ranked_slugs'],
            'same_action':result.get('action')==original['b_action'] and result.get('slug')==original['b_slug'],
            'timings_ms':result['timings_ms'],'processor_forward_ms':dict(measurements),
            'ocr_error':result.get('ocr_error'),'ocr_text_length':len(result.get('ocr_text') or ''),
            'gpu_devices':devices})
        print(json.dumps(output[-1],ensure_ascii=False),flush=True)
    a.output.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
