"""Geometry-only whole-row baseline rectification; fresh OCR must re-prove text."""
import math,re,time
import numpy as np
from PIL import Image
VERSION='robust-quadratic-ink-baseline-v1'

def rectify(pixels,word,deadline=None):
    start=time.perf_counter()
    def no(reason):return None,{'version':VERSION,'accepted':False,'reason':reason,'wall_ms':1000*(time.perf_counter()-start)}
    if deadline is not None and time.perf_counter()>=deadline:return no('deadline_before_rectification')
    a=np.asarray(pixels.convert('L'));match=re.search(r'bbox (\d+) (\d+) (\d+) (\d+)',word.get('title',''))
    if not match:return no('missing_source_word_bounds')
    x1,y1,x2,y2=map(int,match.groups())
    if not (0<x1<x2<a.shape[1] and 0<y1<y2<a.shape[0]) or a.size>1000000:return no('clipped_or_unbounded_source')
    patch=a[y1:y2,x1:x2];hist=np.bincount(patch.ravel(),minlength=256).astype(float)
    prob=hist/hist.sum();c=prob.cumsum();m=(prob*np.arange(256)).cumsum()
    objective=(m[-1]*c-m)**2/(c*(1-c)+1e-12);threshold=int(objective.argmax());ink=patch<=threshold
    counts=ink.sum(axis=0);columns=np.flatnonzero(counts>=max(2,.10*patch.shape[0]))
    if len(columns)<max(12,.5*patch.shape[1]):return no('insufficient_physical_ink_coverage')
    bottom=np.asarray([np.flatnonzero(ink[:,x])[-1]+y1 for x in columns],float)
    nx=2*columns/max(1,patch.shape[1]-1)-1;weights=np.sqrt(counts[columns]).astype(float)
    robust_weights=np.ones(len(columns),float)
    # Lower-envelope quantile regression: open curved glyph sides have upper
    # stroke endings, which are not the physical text baseline. Fixed .90
    # quantile and five bounded iterations retain every observed column.
    for _ in range(5):
        polynomial=np.polyfit(nx,bottom,2,w=weights*robust_weights)
        residual=bottom-np.polyval(polynomial,nx)
        quantile_weight=np.where(residual>=0,.90,.10)
        robust_weights=np.sqrt(quantile_weight/np.maximum(np.abs(residual),1.))
    keep=robust_weights>=float(np.median(robust_weights))
    x=np.clip(np.arange(a.shape[1]),x1,x2-1);logical=2*(x-x1)/max(1,patch.shape[1]-1)-1
    baseline=np.polyval(polynomial,logical);target=float(np.median(baseline[x1:x2]));dy=target-baseline
    if not np.all(np.isfinite(dy)) or np.ptp(dy)>.5*patch.shape[0]:return no('unbounded_baseline_displacement')
    top_pad=max(0,math.ceil(-float(dy.min())));bottom_pad=max(0,math.ceil(float(dy.max())))
    if deadline is not None and time.perf_counter()>=deadline:return no('deadline_before_resampling')
    height=a.shape[0]+top_pad+bottom_pad;out=np.full((height,a.shape[1]),255,dtype=np.uint8);ys=np.arange(height,dtype=float)
    for col in range(a.shape[1]):
        if col%64==0 and deadline is not None and time.perf_counter()>=deadline:return no('deadline_inside_resampling')
        source_y=ys-top_pad-dy[col]
        out[:,col]=np.clip(np.interp(source_y,np.arange(a.shape[0]),a[:,col],left=255,right=255),0,255).astype(np.uint8)
    proof={'version':VERSION,'accepted':True,'reason':'physical_baseline_rectified_not_semantic_evidence','source_word_box':[x1,y1,x2,y2],
      'ink_threshold':threshold,'baseline_quantile':.90,'fit_iterations':5,'baseline_coefficients_normalized_x':polynomial.tolist(),'fit_columns':columns.tolist(),'inlier_columns':columns[keep].tolist(),'robust_fit_weights':robust_weights.tolist(),
      'source_image_size':[int(a.shape[1]),int(a.shape[0])],'rectified_image_size':[int(out.shape[1]),int(out.shape[0])],
      'column_vertical_displacement':dy.tolist(),'top_pad':top_pad,'bottom_pad':bottom_pad,
      'inverse_mapping':'source_x=rectified_x; source_y=rectified_y-top_pad-column_vertical_displacement[source_x]',
      'no_content_removed':True,'confidence_unchanged':True,'same_physical_source_not_independent_vote':True,'wall_ms':1000*(time.perf_counter()-start)}
    return Image.fromarray(out),proof

def inverse_box(box,proof):
    """Conservative enclosure; retain nonlinear map for exact per-edge provenance."""
    x1,y1,x2,y2=box;dy=np.asarray(proof['column_vertical_displacement']);lo=max(0,math.floor(x1));hi=min(len(dy),max(lo+1,math.ceil(x2)))
    displacement=dy[lo:hi]
    return [x1,y1-proof['top_pad']-float(displacement.max()),x2,y2-proof['top_pad']-float(displacement.min())]
