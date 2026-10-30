"""Request-scoped text-only raster normalization; no model/ranking mutation.

Input must be the actual already EXIF-transposed RGB image from core decode.
Pixel-edge coordinates, not pixel-center indices. Evidence stays in the actual
text canvas; mapped coordinates are provenance only, never re-verified glyphs.
"""
import hashlib, math, time
from dataclasses import dataclass
from PIL import Image
VERSION='query-text-canvas-v1-longedge1280'
MAX_LONG_EDGE=1280

@dataclass(frozen=True)
class TextCanvas:
    image: object
    central_box: tuple
    provenance: dict
    def to_decoded_box(self,box):
        _validate_box(box,self.image.size)
        sx,sy=self.provenance['scale_x'],self.provenance['scale_y']
        return [float(box[0])/sx,float(box[1])/sy,float(box[2])/sx,float(box[3])/sy]
    def to_stored_box(self,box):
        d=self.to_decoded_box(box); m=self.provenance.get('decoded_to_stored_matrix')
        if m is None:raise ValueError('Stored EXIF coordinate transform was not provided')
        corners=[(d[0],d[1]),(d[0],d[3]),(d[2],d[1]),(d[2],d[3])]
        xs=[m[0][0]*x+m[0][1]*y+m[0][2] for x,y in corners]
        ys=[m[1][0]*x+m[1][1]*y+m[1][2] for x,y in corners]
        return [min(xs),min(ys),max(xs),max(ys)]

def _validate_box(box,size):
    if len(box)!=4 or any(not math.isfinite(float(v)) for v in box):raise ValueError('Finite4 edge coordinates required')
    if not (0<=box[0]<box[2]<=size[0] and 0<=box[1]<box[3]<=size[1]):raise ValueError('Box outside actual image canvas')

def decoded_to_stored(source_size,orientation,decoded_size):
    w,h=source_size;o=orientation if orientation is not None else 1
    if o not in range(1,9):raise ValueError('Unsupported EXIF orientation')
    expected=(h,w) if o in (5,6,7,8) else (w,h)
    if tuple(decoded_size)!=expected:raise ValueError('EXIF provenance dimensions differ from actual decoded image')
    matrices={1:[[1,0,0],[0,1,0],[0,0,1]],2:[[-1,0,w],[0,1,0],[0,0,1]],
      3:[[-1,0,w],[0,-1,h],[0,0,1]],4:[[1,0,0],[0,-1,h],[0,0,1]],
      5:[[0,1,0],[1,0,0],[0,0,1]],6:[[0,1,0],[-1,0,h],[0,0,1]],
      7:[[0,-1,w],[-1,0,h],[0,0,1]],8:[[0,-1,w],[1,0,0],[0,0,1]]}
    return matrices[o]

def build(decoded_rgb,central_box,*,source_size=None,exif_orientation=None):
    start=time.perf_counter()
    if decoded_rgb.mode!='RGB':raise ValueError('Use core actual EXIF-transposed RGB, not a separate decode')
    w,h=decoded_rgb.size;_validate_box(central_box,(w,h))
    factor=min(1.,MAX_LONG_EDGE/max(w,h));nw=max(1,round(w*factor));nh=max(1,round(h*factor))
    image=decoded_rgb if (nw,nh)==(w,h) else decoded_rgb.resize((nw,nh),Image.Resampling.LANCZOS)
    sx,sy=nw/w,nh/h
    box=(max(0,math.floor(central_box[0]*sx)),max(0,math.floor(central_box[1]*sy)),
         min(nw,math.ceil(central_box[2]*sx)),min(nh,math.ceil(central_box[3]*sy)))
    _validate_box(box,image.size)
    p={'version':VERSION,'scope':'word_character_semantic_OCR_only; visual/detector/encoder/ranking images untouched',
       'input_coordinate_space':'decoded_EXIF_RGB_pixel_edges','evidence_coordinate_space':'text_canvas_pixel_edges',
       'decoded_size':[w,h],'text_canvas_size':[nw,nh],'max_long_edge':MAX_LONG_EDGE,'upsampled':False,
       'resampling':'LANCZOS' if image is not decoded_rgb else 'identity',
       'scale_x':sx,'scale_y':sy,'decoded_to_text_matrix':[[sx,0,0],[0,sy,0],[0,0,1]],
       'text_to_decoded_matrix':[[1/sx,0,0],[0,1/sy,0],[0,0,1]],
       'central_box_decoded':list(central_box),'central_box_text':list(box),
       'central_box_rounding':'outward floor left/top,ceil right/bottom; clipped only to actual canvas',
       'text_canvas_rgb_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
       'mapped_boxes_are_provenance_only':True,'same_physical_view_not_independent_OCR_vote':True,
       'title_acquisition_and_title_model_crop_normalized':False}
    if source_size is not None:
        p.update(source_stored_size=list(source_size),exif_orientation=exif_orientation,
          decoded_to_stored_matrix=decoded_to_stored(source_size,exif_orientation,(w,h)))
    p['preprocessing_wall_ms']=round(1000*(time.perf_counter()-start),3)
    return TextCanvas(image,box,p)
