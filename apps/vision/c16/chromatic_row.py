"""Fixed pre-confidence chromatic projection. No token or case input."""
import numpy as np
from PIL import Image,ImageFilter,ImageOps
VERSION='max_robust_local_ink_contrast_RGB_L_saturation_opponents-v1-unvalidated'
def project(image):
    image=image.convert('RGB');channels=[('L',image.convert('L'))]+[(name,image.getchannel(name)) for name in ('R','G','B')];scores=[]
    rgb=np.asarray(image,dtype=np.float32);maximum=rgb.max(2);minimum=rgb.min(2)
    channels.append(('saturation',Image.fromarray(np.uint8(np.divide(255*(maximum-minimum),maximum,out=np.zeros_like(maximum),where=maximum>0)))))
    for a,b,name in ((0,1,'R_minus_G'),(2,0,'B_minus_R'),(1,2,'G_minus_B')):
        channels.append((name,Image.fromarray(np.uint8((rgb[:,:,a]-rgb[:,:,b]+255)/2))))
    for name,pixels in channels:
        a=np.asarray(pixels,dtype=np.float32);background=np.asarray(pixels.filter(ImageFilter.GaussianBlur(3)),dtype=np.float32)
        # Robust local contrast, fixed ordering settles ties. No semantic OCR,
        # color-name condition, candidate/model score or confidence enters.
        difference=np.abs(a-background);score=float(np.quantile(difference,.90))
        scores.append({'channel':name,'score':score})
    winner=max(range(len(scores)),key=lambda i:(scores[i]['score'],-i));name,pixels=channels[winner]
    pixels=ImageOps.autocontrast(pixels)
    if float(np.median(np.asarray(pixels)))<128:pixels=ImageOps.invert(pixels)
    return pixels,{'version':VERSION,'selected_channel':name,'scores':scores,'selection_before_OCR_confidence':True,'source_color_content_unchanged_for_visual_pipeline':True}
