"""Complementary source-bound upper-view appearance, never wine colour evidence."""
import hashlib
import numpy as np
VERSION='upper-conditional-chromatic-artwork-v3-achromatic-competitors-retained'
BINS=24;MIN_SATURATION=.25;MIN_VALUE=.15;MIN_CHROMATIC_AREA=.15
MIN_SIMILARITY=.70;MIN_MARGIN=.05

def descriptor(rgb,role="query"):
 if role not in ("query","reference"):raise ValueError("Explicit source crop role required")
 a=np.asarray(rgb.convert('RGB') if hasattr(rgb,'convert') else rgb,dtype=np.uint8)
 if a.ndim!=3 or a.shape[2]!=3 or not a.size:raise ValueError('Actual RGB crop required')
 v=a.astype(np.float64)/255;hi=v.max(2);lo=v.min(2);delta=hi-lo;s=np.divide(delta,hi,out=np.zeros_like(hi),where=hi>0);h=np.zeros_like(hi);active=delta>0
 for channel in range(3):
  mask=active&(v.argmax(2)==channel)
  if channel==0:x=(v[:,:,1]-v[:,:,2])/np.where(active,delta,1)
  elif channel==1:x=(v[:,:,2]-v[:,:,0])/np.where(active,delta,1)+2
  else:x=(v[:,:,0]-v[:,:,1])/np.where(active,delta,1)+4
  h[mask]=x[mask]
 h=(h/6)%1;mask=(s>=MIN_SATURATION)&(hi>=MIN_VALUE);area=float(mask.mean())
 raw=np.bincount(np.minimum(BINS-1,np.floor(h[mask]*BINS).astype(int)),weights=(s*hi)[mask],minlength=BINS).astype(np.float64)
 smooth=np.roll(raw,1)+2*raw+np.roll(raw,-1);total=float(smooth.sum());prob=smooth/total if total else smooth
 luma=.299*v[:,:,0]+.587*v[:,:,1]+.114*v[:,:,2];contrast=float(255*(np.percentile(luma,95)-np.percentile(luma,5)));ready=bool(area>=MIN_CHROMATIC_AREA and total>0) if role=='query' else bool(contrast>=35)
 return {'version':VERSION,'accepted':ready,'role':role,'contrast_q95_q05':contrast,'empty_reference_chromatic_histogram_observed':bool(role=='reference' and total==0),'reason':None if ready else ('insufficient_query_chromatic_area' if role=='query' else 'reference_sourcecrop_contrast_below35'),'chromatic_area_fraction':area,'histogram':prob.tolist(),'crop_RGB_sha256':hashlib.sha256(a.tobytes()).hexdigest(),'crop_shape':list(a.shape),'physical_evidence':'same_upper_view_complementary_not_independent_vote','wine_attribute_inference':False}

def select(query,references,upper_siglip,required_indices,source_bound):
 required=list(required_indices)
 if len(set(required))!=len(required) or not required or not query.get('accepted'):return {'override':False,'reason':'unready_query_or_duplicate_required_scope'}
 if set(references)!=set(required) or set(upper_siglip)!=set(required) or set(source_bound)!=set(required):return {'override':False,'reason':'all_compatible_contenders_must_participate'}
 q=np.asarray(query['histogram'],dtype=float);scores={}
 if q.shape!=(BINS,) or not np.isfinite(q).all() or (q<0).any() or abs(float(q.sum())-1)>1e-6:raise ValueError('Invalid query histogram')
 for i in required:
  r=references[i];binding=source_bound[i]
  if not r.get('accepted') or any(not binding.get(k) for k in ('catalog_sha256','slug','reference_sha256','upper_crop_RGB_sha256','gallery_manifest_sha256')) or binding['upper_crop_RGB_sha256']!=r.get('crop_RGB_sha256'):return {'override':False,'reason':'unready_or_unbound_compatible_reference','index':int(i)}
  p=np.asarray(r['histogram'],dtype=float);sig=float(upper_siglip[i])
  if p.shape!=(BINS,) or not np.isfinite(p).all() or (p<0).any() or not (abs(float(p.sum())-1)<=1e-6 or (r.get('empty_reference_chromatic_histogram_observed') is True and float(p.sum())==0)) or not np.isfinite(sig):raise ValueError('Invalid reference feature')
  scores[i]=float(np.sqrt(q*p).sum())
 ordered=sorted(required,key=lambda i:(-scores[i],int(i)));winner=ordered[0];margin=scores[winner]-(scores[ordered[1]] if len(ordered)>1 else 0.)
 visual=max(float(upper_siglip[i]) for i in required);visual_winners=[i for i in required if float(upper_siglip[i])==visual]
 accepted=bool(len(required)>1 and scores[winner]>=MIN_SIMILARITY and margin>=MIN_MARGIN and visual_winners==[winner] and visual>=MIN_SIMILARITY)
 return {'override':accepted,'selected_index':int(winner) if accepted else None,'reason':'verified_complementary_upper_artwork' if accepted else 'appearance_or_shared_visual_margin_not_verified','scores':{str(i):scores[i] for i in required},'margin':float(margin),'min_similarity':MIN_SIMILARITY,'min_margin':MIN_MARGIN,'highest_existing_upperSigLIP_required':True,'correlation_group':'same_physical_upper_crop','version':VERSION}
