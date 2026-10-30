"""Source-bound upper bottle appearance; never asserts complete physical cap.
Source edges disclosed; same-object geometry nominations require catalogue QA.
"""
import math
VERSION='source_bound_upper_bottle_visual_top35-v6-rounding-fragments'
FRACTION=.35
SAME_OBJECT_IOU=.90
FRAGMENT_ROUNDING_PIXELS=1
MAX_FRAGMENT_OUTER_AREA_FRACTION=.5

def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)

def nominate_reference(decoded_size,detections,source_sha256,actual_trace):
    result={'accepted_nomination':False,'decoded_size':list(decoded_size),'source_sha256':source_sha256,'detections':detections,'trace':actual_trace,'same_object_iou':SAME_OBJECT_IOU,'complete_cap_asserted':False}
    def stop(reason):return dict(result,reason=reason)
    if len(decoded_size)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in decoded_size):return stop('invalid_source_size')
    if actual_trace.get('source_sha256')!=source_sha256 or not actual_trace.get('trace_path') or not actual_trace.get('trace_sha256'):return stop('missing_source_actual_detector_trace')
    w,h=decoded_size;boxes=[]
    for d in detections:
        b=d.get('box') if isinstance(d,dict) else None
        if not isinstance(b,list) or len(b)!=4 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in b) or not (0<=b[0]<b[2]<=w and 0<=b[1]<b[3]<=h):return stop('invalid_or_outside_detection')
        boxes.append([float(x) for x in b])
    if not boxes:return stop('no_bottle_detection')
    # Remove strict contained fragments, then complete-link cluster only near
    # identical maximal nominations. No transitive overlap chains/brand rules.
    def fragment_inside(b,p):
        if p==b:return False
        strict=p[0]<=b[0] and p[1]<=b[1] and p[2]>=b[2] and p[3]>=b[3]
        area=(b[2]-b[0])*(b[3]-b[1]);outer=(p[2]-p[0])*(p[3]-p[1])
        rounded=(p[0]-FRAGMENT_ROUNDING_PIXELS<=b[0] and p[1]-FRAGMENT_ROUNDING_PIXELS<=b[1] and p[2]+FRAGMENT_ROUNDING_PIXELS>=b[2] and p[3]+FRAGMENT_ROUNDING_PIXELS>=b[3] and area<=MAX_FRAGMENT_OUTER_AREA_FRACTION*outer)
        return strict or rounded
    discarded=[{'box':b,'reason':'strict_or_one_sourcepixel_rounded_halfarea_fragment'} for i,b in enumerate(boxes) if any(fragment_inside(b,p) for j,p in enumerate(boxes) if j!=i)]
    maximal=[b for i,b in enumerate(boxes) if not any(fragment_inside(b,p) for j,p in enumerate(boxes) if j!=i)]
    ordered=sorted(maximal,key=lambda b:(-(b[2]-b[0])*(b[3]-b[1]),*b));clusters=[]
    for b in ordered:
        hits=[c for c in clusters if all(iou(b,p)>=SAME_OBJECT_IOU for p in c)]
        if len(hits)>1:return stop('ambiguous_same_object_cluster')
        if hits:hits[0].append(b)
        else:clusters.append([b])
    result.update(maximal_clusters=clusters,discarded_strict_fragments=len(boxes)-len(maximal),discarded_fragment_observations=discarded,fragment_rounding_pixels=FRAGMENT_ROUNDING_PIXELS,max_fragment_outer_area_fraction=MAX_FRAGMENT_OUTER_AREA_FRACTION)
    if len(clusters)!=1:return stop('multiple_physical_bottle_nominations_abstain')
    b=clusters[0][0]
    return dict(result,accepted_nomination=True,bottle_box=b,source_edges_contacted=[k for k,t in [('left',b[0]==0),('top',b[1]==0),('right',b[2]==w),('bottom',b[3]==h)] if t],reason='unique_same_object_upper_view_nomination_pending_source_coverage_QA')

def propose(decoded_size,bottle_box,source_sha256,source_observation):
    result={'version':VERSION,'accepted':False,'source_sha256':source_sha256,'decoded_size':list(decoded_size),'bottle_box':list(bottle_box),'complete_cap_asserted':False,'wine_attribute_inference':False,'source_observation':source_observation}
    def stop(reason):return dict(result,reason=reason)
    if len(decoded_size)!=2 or len(bottle_box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in (*decoded_size,*bottle_box)):return stop('invalid_geometry')
    w,h=decoded_size;x1,y1,x2,y2=bottle_box
    if not (0<=x1<x2<=w and 0<=y1<y2<=h):return stop('geometry_outside_actual_source')
    p=source_observation
    if p.get('source_sha256')!=source_sha256 or p.get('decoded_size')!=list(decoded_size) or p.get('observed_bottle_box')!=list(bottle_box) or not p.get('actual_detector_trace_path') or not p.get('actual_detector_trace_sha256'):return stop('missing_source_coordinate_detector_binding')
    if not p.get('evidence_path') or not p.get('evidence_sha256') or p.get('one_dominant_physical_bottle_observed') is not True or p.get('usable_upper_bottle_appearance_observed') is not True or p.get('foreign_or_fragment_only_product_image') is not False:return stop('source_coverage_or_single_object_uncertain')
    return dict(result,accepted=True,box=[math.floor(x1),math.floor(y1),math.ceil(x2),math.ceil(y1+FRACTION*(y2-y1))],source_edges_contacted=[k for k,t in [('left',x1==0),('top',y1==0),('right',x2==w),('bottom',y2==h)] if t],source_coordinate_space='EXIF_decoded_original_pixel_edges',source_crop_coverage='top35% of actual observed detector box, not physical-cap completeness',reason='source_bound_independent_upper_bottle_appearance_view')
