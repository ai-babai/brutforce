"""Measured existing-model geometry and actual upper RGB crop quality.
This is not physical complete-cap certainty or wine-attribute evidence.
Thresholds explicitly predeclared before new encoder probe; no OCR/model here.
"""
import math,hashlib,json
import numpy as np
from upper_geometry import FRACTION,VERSION,nominate_reference,iou,SAME_OBJECT_IOU
MIN_ASPECT=2.;MIN_SOURCE_HEIGHT_FRACTION=.70;MIN_SOURCE_AREA_FRACTION=.30;MIN_CONTRAST=35.

def measured(image,box):
    w,h=image.size;x1,y1,x2,y2=box
    crop_box=[math.floor(x1),math.floor(y1),math.ceil(x2),math.ceil(y1+FRACTION*(y2-y1))]
    rgb=image.convert('RGB').crop(crop_box);gray=np.asarray(rgb.convert('L'),dtype=np.float32)
    lo,hi=np.quantile(gray,[.05,.95]);bw=x2-x1;bh=y2-y1
    return {'decoded_size':[w,h],'box':crop_box,'bottle_aspect_height_width':float(bh/bw),'bottle_height_source_height':float(bh/h),'bottle_area_source_area':float(bw*bh/(w*h)),'contrast_q05':float(lo),'contrast_q95':float(hi),'contrast_q95_minus_q05':float(hi-lo),'contrast_projection':'PIL_RGB_to_L_fixed_luma','upper_rgb_crop_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),'upper_rgb_crop_size':list(rgb.size),'source_edges_contacted':[k for k,t in [('left',x1==0),('top',y1==0),('right',x2==w),('bottom',y2==h)] if t]}

def reference(image,source_sha256,actual_trace):
    size=list(image.size);n=nominate_reference(size,actual_trace.get('detections',[]),source_sha256,actual_trace);result={'status':'MODEL_GEOMETRY_AND_CROP_QUALITY','accepted':False,'source_sha256':source_sha256,'nomination':n,'complete_physical_cap_asserted':False,'wine_attribute_inference':False,'thresholds':{'aspect_min':MIN_ASPECT,'source_height_fraction_min':MIN_SOURCE_HEIGHT_FRACTION,'source_area_fraction_min':MIN_SOURCE_AREA_FRACTION,'contrast_min':MIN_CONTRAST},'version':VERSION,'actual_trace':actual_trace}
    if actual_trace.get('decoded_size')!=size or not n['accepted_nomination']:return dict(result,reason='source_or_unique_physical_object_geometry_uncertain')
    m=measured(image,n['bottle_box']);result['measured']=m
    tests={'full_bottle_model_aspect':m['bottle_aspect_height_width']>=MIN_ASPECT,'dominant_model_height':m['bottle_height_source_height']>=MIN_SOURCE_HEIGHT_FRACTION,'dominant_model_area':m['bottle_area_source_area']>=MIN_SOURCE_AREA_FRACTION,'visible_upper_crop_contrast':m['contrast_q95_minus_q05']>=MIN_CONTRAST};result['actual_checks']=tests
    return dict(result,accepted=all(tests.values()),reason='predeclared_model_geometry_and_source_crop_quality' if all(tests.values()) else 'programmatic_source_quality_insufficient_abstain')

def query(image,source_sha256,central_box,actual_trace):
    result={'version':VERSION,'status':'MODEL_GEOMETRY_AND_CROP_QUALITY','accepted':False,'source_sha256':source_sha256,'complete_physical_cap_asserted':False,'wine_attribute_inference':False,'actual_trace':actual_trace,'bottle_box':list(central_box)}
    w,h=image.size
    if actual_trace.get('source_sha256')!=source_sha256 or actual_trace.get('decoded_size')!=[w,h] or not actual_trace.get('trace_path') or not actual_trace.get('trace_sha256'):return dict(result,reason='query_actual_detector_source_binding_missing')
    if len(central_box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in central_box) or not (0<=central_box[0]<central_box[2]<=w and 0<=central_box[1]<central_box[3]<=h):return dict(result,reason='invalid_actual_central_bottle_scope')
    if actual_trace.get('observed_central_box')!=list(central_box):return dict(result,reason='central_box_not_actual_observed_selection')
    if not isinstance(actual_trace.get('detections'),list):return dict(result,reason='all_actual_detector_proposals_unobserved')
    m=measured(image,central_box);result['measured']=m;upper=m['box'];foreign=[]
    for d in actual_trace.get('detections',[]):
        b=d.get('box',[])
        if len(b)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in b):return dict(result,reason='query_detection_geometry_unknown')
        same=(iou(b,central_box)>=SAME_OBJECT_IOU or (central_box[0]<=b[0] and central_box[1]<=b[1] and central_box[2]>=b[2] and central_box[3]>=b[3]))
        cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        if not same and upper[0]<=cx<=upper[2] and upper[1]<=cy<=upper[3]:foreign.append(b)
    if foreign:return dict(result,reason='other_physical_bottle_center_inside_upper_query_view',foreign_detections=foreign)
    passed=m['contrast_q95_minus_q05']>=MIN_CONTRAST
    return dict(result,accepted=passed,reason='actual_central_upper_view_source_contrast' if passed else 'query_upper_view_contrast_insufficient_abstain')

def view_geometry(quality,evidence_path,evidence_sha256):
    if not evidence_path or not evidence_sha256:return {'version':VERSION,'accepted':False,'reason':'missing_persisted_source_quality_evidence'}
    if not quality.get('accepted'):return {'version':VERSION,'accepted':False,'source_sha256':quality.get('source_sha256'),'reason':quality.get('reason'),'quality':quality}
    m=quality['measured'];return {'version':VERSION,'accepted':True,'source_sha256':quality['source_sha256'],'box':m['box'],'decoded_size':m['decoded_size'],'upper_rgb_crop_sha256':m['upper_rgb_crop_sha256'],'source_edges_contacted':m['source_edges_contacted'],'quality':quality,'evidence_path':evidence_path,'evidence_sha256':evidence_sha256,'complete_cap_asserted':False,'evidence_contract':'MODEL_GEOMETRY_AND_CROP_QUALITY_NOT_CAP_COMPLETENESS'}
