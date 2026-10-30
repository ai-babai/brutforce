"""Bounded projection-band physical row proposals without lexical seed.
No global connected components or cap relaxation; nomination is not proof.
"""
import math,time
import numpy as np
from PIL import Image,ImageFilter
VERSION='local_horizontal_ink_projection_bands-v1-unvalidated'
def propose(image,deadline=None,max_rows=2):
    scale=min(1.,256/image.width,1536/image.height);small=image.convert('RGB').resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS);a=np.asarray(small,dtype=np.float32);signals=[a[:,:,i] for i in range(3)]
    maximum=a.max(2);minimum=a.min(2);signals.append(np.divide(255*(maximum-minimum),maximum,out=np.zeros_like(maximum),where=maximum>0))
    for i,j in ((0,1),(2,0),(1,2)):signals.append((a[:,:,i]-a[:,:,j]+255)/2)
    contrast=np.zeros(a.shape[:2],dtype=np.float32)
    for signal in signals:
        if deadline is not None and time.perf_counter()>=deadline:return [],{'version':VERSION,'aborted':True,'reason':'projection_budget_exhausted'}
        bg=np.asarray(Image.fromarray(np.uint8(signal)).filter(ImageFilter.GaussianBlur(3)),dtype=np.float32);contrast=np.maximum(contrast,np.abs(signal-bg))
    threshold=max(8.,float(np.quantile(contrast,.90)));mask=contrast>threshold;occupancy=mask.mean(1);ys=occupancy>.04;bands=[];start=None
    for y,active in enumerate(ys):
        if deadline is not None and y%64==0 and time.perf_counter()>=deadline:return [],{'version':VERSION,'aborted':True,'reason':'band_budget_exhausted'}
        if active and start is None:start=y
        if start is not None and (not active or y==len(ys)-1):
            end=y if not active else y+1;bands.append([start,end]);start=None
    # Group immediately adjacent strokes/diacritics with bounded2pixel gaps.
    merged=[]
    for b in bands:
        if merged and b[0]-merged[-1][1]<=2:merged[-1][1]=b[1]
        else:merged.append(b)
    result=[]
    for n,(top,bottom) in enumerate(merged):
        height=bottom-top
        if not 3<=height<=max(3,.1*small.height):continue
        ys0,xs=np.where(mask[top:bottom]);
        if not len(xs):continue
        left=int(xs.min());right=int(xs.max())+1
        if right-left<3*height:continue
        above=merged[n-1][1] if n else 0;below=merged[n+1][0] if n+1<len(merged) else small.height
        padded_top=max(0,top-.5*height,(above+top)/2);padded_bottom=min(small.height,bottom+.5*height,(bottom+below)/2)
        sx=image.width/small.width;sy=image.height/small.height;box=[max(0,math.floor((left-.5*height)*sx)),max(0,math.floor(padded_top*sy)),min(image.width,math.ceil((right+.5*height)*sx)),min(image.height,math.ceil(padded_bottom*sy))]
        score=float(contrast[top:bottom,left:right].mean())*(right-left)/height
        result.append({'box':box,'nomination_role':'independent_physical_ink_row_no_lexical_seed','raw_location_only':True,'geometry_version':VERSION,'score':score,'connected_components_computed':False,'neighbor_boundaries':[above,below]})
    return sorted(result,key=lambda r:(-r['score'],r['box'][1],r['box'][0]))[:max_rows],{'version':VERSION,'aborted':False,'threshold':threshold,'projection_size':list(small.size),'source_scale':[image.width/small.width,image.height/small.height],'bands':len(merged),'selected_rows':min(max_rows,len(result)),'maximum_rows':max_rows,'global_component_caps_unchanged':True}
