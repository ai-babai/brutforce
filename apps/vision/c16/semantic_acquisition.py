"""Bounded geometry-driven descriptor reacquisition, existing Tesseract only."""
import csv,io,math,os,re,subprocess,time
from html.parser import HTMLParser
import numpy as np
from PIL import Image,ImageFilter,ImageOps
from semantic_evidence import complete_descriptor,verify_word,VERSION
class Hocr(HTMLParser):
    def __init__(self):super().__init__();self.stack=[];self.words=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.stack.append((tag,a))
        if a.get('class')=='ocrx_word':self.words.append({'title':a.get('title',''),'chars':[]})
    def handle_endtag(self,tag):
        if self.stack:self.stack.pop()
    def handle_data(self,data):
        if data.strip() and self.stack and self.stack[-1][1].get('class')=='ocrx_cinfo' and self.words:self.words[-1]['chars'].append({'char':data,'title':self.stack[-1][1].get('title','')})

def acquire(image,box,assets,pass_words=(),budget_ms=900,max_calls=4):
    start=time.perf_counter();deadline=start+budget_ms/1000;calls=[];errors=[];evidence=[];accepted={'color':set(),'sugar':set(),'grape':set()};exhausted=False;proposal_stats=[]
    x1,y1,x2,y2=map(int,box);bw=x2-x1;bh=y2-y1
    body_box=[max(0,math.floor(x1+.06*bw)),max(0,math.floor(y1+.30*bh)),min(image.width,math.ceil(x1+.94*bw)),min(image.height,y2)]
    body=image.crop(body_box).convert('L')
    script=''.join(w.get('text','') for words in pass_words for w in words)
    cyr=sum('а'<=c.lower()<='я' or c.lower()=='ё' for c in script);latin=sum('a'<=c.lower()<='z' for c in script)
    language='rus' if cyr>latin else 'eng'
    env=dict(os.environ,TESSDATA_PREFIX=assets['tessdata_dir'],OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
    def call(roi,kind,psm,source_box,transform,group):
        nonlocal exhausted
        remaining=deadline-time.perf_counter()
        if len(calls)>=max_calls or remaining<=0:exhausted=True;return None
        stream=io.BytesIO();roi.save(stream,format='PNG');remaining=deadline-time.perf_counter()
        if remaining<=0:exhausted=True;return None
        record={'index':len(calls),'kind':kind,'psm':psm,'language':language,'source_box':source_box,'transform':transform,'correlation_group':group,'timeout_ms':remaining*1000,'errors':[]};calls.append(record);t=time.perf_counter()
        try:
            options=['-c','tessedit_create_tsv=1'] if kind=='location_tsv' else ['-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1']
            p=subprocess.run([assets['tesseract'],'stdin','stdout','-l',language,'--psm',str(psm)]+options,input=stream.getvalue(),capture_output=True,timeout=remaining,env=env)
            if p.returncode:raise RuntimeError('Tesseract nonzero exit: '+str(p.returncode))
            text=p.stdout.decode()
            if not text.strip():raise ValueError('empty OCR output')
            return text
        except Exception as exc:
            error={'call':record['index'],'type':type(exc).__name__,'message':str(exc)[:300]};errors.append(error);record['errors'].append(error)
            if isinstance(exc,subprocess.TimeoutExpired):exhausted=True
            return None
        finally:record['wall_ms']=(time.perf_counter()-t)*1000
    # Position descriptors in one fresh TSV pass. Existing pass words do not
    # carry source boxes; their confidence is not repeated as an independent vote.
    scale=min(2,2000/max(body.size));location=ImageOps.autocontrast(body).resize((round(body.width*scale),round(body.height*scale)),Image.Resampling.LANCZOS)
    text=call(location,'location_tsv',11,body_box,{'scale':scale,'border':0},'selected-bottle-body')
    words=[]
    if text:
        try:
            for r in csv.DictReader(io.StringIO(text),delimiter='\t',quoting=csv.QUOTE_NONE):
                if r.get('level')=='5' and r.get('text','').strip():
                    b=[int(r['left']),int(r['top']),int(r['width']),int(r['height'])];q=float(r['conf']);coords=[body_box[0]+b[0]/scale,body_box[1]+b[1]/scale,body_box[0]+(b[0]+b[2])/scale,body_box[1]+(b[1]+b[3])/scale]
                    words.append({'text':r['text'],'confidence':q,'box':b,'original_box':coords})
            calls[-1]['words']=words
        except Exception as exc:errors.append({'call':0,'type':type(exc).__name__,'message':'invalid TSV: '+str(exc)[:200]})
    anchors=[w for w in words if w['confidence']>=60 and complete_descriptor(w['text'])]
    # Confidence >=60 nominates location only. Choose original geometric order,
    # deduplicate overlapping row proposals before any additional OCR call.
    proposals=[];proposal_heights=[]
    for w in sorted(anchors,key=lambda w:(w['box'][1],w['box'][0])):
        x,y,ww,h=[v/scale for v in w['box']]
        b=[0,max(0,round(y-.15*h)),body.width,min(body.height,round(y+1.25*h))]
        # Derive horizontal extent from foreground column components around
        # the anchor, with symmetric gaps bounded by observed glyph height.
        line=body.crop(b);a=np.asarray(line,dtype=np.float32);bg=np.asarray(line.filter(ImageFilter.GaussianBlur(3)),dtype=np.float32)
        foreground=(a-bg>8) if np.median(a)<128 else (a-bg< -8)
        # Derive text extent from interior strokes. Boundary-clipped outlines
        # and short noise cannot define the line's horizontal support.
        filtered=np.zeros_like(foreground);remaining=foreground.copy();points=np.argwhere(remaining)
        visited=0
        for yy,xx in points:
            if time.perf_counter()>=deadline or visited>50000:exhausted=True;break
            if not remaining[yy,xx]:continue
            todo=[(int(yy),int(xx))];remaining[yy,xx]=False;component=[]
            while todo:
                cy,cx=todo.pop();component.append((cy,cx));visited+=1
                if visited%128==0 and (time.perf_counter()>=deadline or visited>50000):exhausted=True;break
                for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                    ny,nx=cy+dy,cx+dx
                    if 0<=ny<remaining.shape[0] and 0<=nx<remaining.shape[1] and remaining[ny,nx]:remaining[ny,nx]=False;todo.append((ny,nx))
            if exhausted:break
            ys=[v[0] for v in component];xs=[v[1] for v in component]
            outline=max(ys)-min(ys)+1>=.9*line.height and max(xs)-min(xs)+1>=.8*h
            interior=min(ys)>0 and max(ys)<line.height-1 and max(ys)-min(ys)+1>=.5*h
            if len(component)>=3 and not outline and interior:
                for cy,cx in component:filtered[cy,cx]=True
        if exhausted:break
        active=np.flatnonzero(np.sum(filtered,axis=0)>=max(2,math.ceil(line.height*.05)))
        clusters=[]
        for column in active:
            column=int(column)
            if clusters and column-clusters[-1][1]<=h:clusters[-1][1]=column
            else:clusters.append([column,column])
        containing=[c for c in clusters if c[0]<=x+ww/2<=c[1]]
        if len(containing)==1:
            lo,hi=containing[0];b[0]=max(0,math.floor(lo-.5*h));b[2]=min(body.width,math.ceil(hi+1+.5*h))
        if any(max(0,min(b[3],p[3])-max(b[1],p[1]))>=.5*min(b[3]-b[1],p[3]-p[1]) for p in proposals):continue
        if b[2]>b[0] and b[3]>b[1]:
            proposals.append(b);proposal_heights.append(h);proposal_stats.append({'anchor':w,'component_pixels_visited':visited,'max_component_pixels':50000,'component_clusters':clusters,'box_in_body':b,'symmetric_padding_heights':[.5,1.0]})
    for n,b in enumerate(proposals[:2]):
        if time.perf_counter()>=deadline:exhausted=True;break
        source=[body_box[0]+b[0],body_box[1]+b[1],body_box[0]+b[2],body_box[1]+b[3]];group='selected-bottle-row:'+','.join(map(str,source[1::2]))
        gray=body.crop(b).resize(((b[2]-b[0])*3,(b[3]-b[1])*3),Image.Resampling.LANCZOS)
        bright=bool(np.median(np.asarray(gray))<128)
        # Two deterministic correlated ink reconstructions: stroke closing and
        # local foreground residual. Neither creates an independent OCR vote.
        bold=gray.filter(ImageFilter.MaxFilter(3) if bright else ImageFilter.MinFilter(3))
        a=np.asarray(gray,dtype=np.float32);bg=np.asarray(gray.filter(ImageFilter.GaussianBlur(9)),dtype=np.float32);mask=(a-bg>8) if bright else (a-bg< -8)
        binary=Image.fromarray(np.uint8(mask)*255)
        variants=[('stroke_closing',ImageOps.invert(ImageOps.autocontrast(bold)) if bright else ImageOps.autocontrast(bold)),('local_foreground',ImageOps.invert(binary))]
        # One optional symmetric border repair after incomplete evidence.
        border_box=[max(0,math.floor(b[0]-.5*proposal_heights[n])),b[1],min(body.width,math.ceil(b[2]+.5*proposal_heights[n])),b[3]]
        repair=body.crop(border_box).resize(((border_box[2]-border_box[0])*3,(border_box[3]-border_box[1])*3),Image.Resampling.LANCZOS)
        ra=np.asarray(repair,dtype=np.float32);rb=np.asarray(repair.filter(ImageFilter.GaussianBlur(9)),dtype=np.float32);rm=(ra-rb>8) if bright else (ra-rb< -8)
        variants.append(('symmetric_border_repair',ImageOps.invert(Image.fromarray(np.uint8(rm)*255))))
        for method,roi in variants:
            if method=='symmetric_border_repair':
                if accepted['color'] and accepted['sugar']:continue
                source=[body_box[0]+border_box[0],body_box[1]+border_box[1],body_box[0]+border_box[2],body_box[1]+border_box[3]]
            roi=ImageOps.expand(roi,border=16,fill=255)
            hocr=call(roi,method,7,source,{'scale':3,'border':16},group)
            if hocr is None:continue
            parser=Hocr()
            try:parser.feed(hocr)
            except Exception as exc:errors.append({'call':len(calls)-1,'type':type(exc).__name__,'message':'invalid hOCR'});continue
            call_evidence=[]
            for word in parser.words:
                item=verify_word(word,roi);confidence=re.search(r'x_wconf ([0-9.]+)',word['title'])
                item.update(word_confidence=float(confidence[1]) if confidence else None,word_title=word['title'],call_index=len(calls)-1,correlation_group=group,source_box=source,raw_hocr_chars=word['chars'])
                for char in word['chars']:
                    match=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',char.get('title',''))
                    if match:
                        z=list(map(int,match.groups()));char['original_box']=[source[0]+(z[0]-16)/3,source[1]+(z[1]-16)/3,source[0]+(z[2]-16)/3,source[1]+(z[3]-16)/3]
                evidence.append(item);call_evidence.append(item)
                if item['accepted']:accepted[item['key']].add(item['value'])
            calls[-1]['evidence']=call_evidence
    wall=(time.perf_counter()-start)*1000
    return {'version':VERSION,'accepted_fields':{k:sorted(v) for k,v in accepted.items()},'evidence':evidence,'calls':calls,'errors':errors,'budget':{'limit_ms':budget_ms,'max_calls':max_calls,'calls':len(calls),'exhausted':bool(exhausted or wall>budget_ms),'returned_wall_ms':wall,'drained_wall_ms':wall,'synchronous_drained':True},'fallback_reason':'accepted_complete_descriptors' if any(accepted.values()) else ('budget_exhausted' if exhausted else 'no_geometry_verified_complete_descriptor'),'body_box':body_box,'proposals':proposal_stats}
