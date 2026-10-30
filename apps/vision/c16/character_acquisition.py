"""Bounded CPU hOCR acquisition from generic local-contrast word proposals."""
import io, itertools, math, os, re, subprocess, time
from html.parser import HTMLParser
import numpy as np
from PIL import Image, ImageFilter, ImageOps
from gram_ocr import norm, ALIASES
from candidate_policy import GRAPE_ALIASES
from character_evidence import VERSION, inspect_char_run

class Hocr(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.words=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);self.stack.append((tag,attrs))
        if attrs.get('class')=='ocrx_word':self.words.append({'title':attrs.get('title',''),'chars':[]})
    def handle_endtag(self,tag):
        if self.stack:self.stack.pop()
    def handle_data(self,data):
        if not data.strip() or not self.stack:return
        attrs=self.stack[-1][1]
        if attrs.get('class')=='ocrx_cinfo' and self.words:
            self.words[-1]['chars'].append({'char':data,'title':attrs.get('title','')})

def grape_alias_lexicon(catalog):
    """Global catalog lexicon, with explicit canonical multilingual synonyms."""
    reverse={}
    for alias,value in dict(ALIASES,**GRAPE_ALIASES).items():reverse.setdefault(value,set()).add(alias)
    result={}
    for grape in sorted(catalog.vocab):
        choices=[sorted({t}|reverse.get(t,set())) for t in norm(grape).split()]
        for terms in itertools.product(*choices):
            # A phrase keeps word boundaries. Fragment matching cannot bridge a
            # space and cannot reinterpret short codes or fuzzy spellings.
            result.setdefault(' '.join(terms),set()).add(grape)
    # An alias shared by canonical rows remains explicitly ambiguous.
    return result

def global_unique_fragments(chars,lexicon):
    flattened={alias:grape for alias,values in lexicon.items() for grape in values if len(values)==1}
    # Preserve ambiguity also where the same exact alias denotes several rows.
    ambiguous=[alias for alias,values in lexicon.items() if len(values)>1]
    accepted=inspect_char_run(chars,flattened)
    return [m for m in accepted if not any(m['fragment'] in alias for alias in ambiguous)]

def word_proposals(body, limit=4, deadline=None, max_foreground=100000,
                   max_components=1024, max_pairs=100000):
    stats={'visited_pixels':0,'components_discovered':0,'merge_pairs':0,
           'max_foreground':max_foreground,'max_components':max_components,
           'max_merge_pairs':max_pairs,'aborted':False,'abort_reason':None}
    def abort(reason):
        stats.update(aborted=True,abort_reason=reason)
        return [],stats
    def expired():return deadline is not None and time.perf_counter()>=deadline
    if expired():return abort('deadline_before_proposals')
    gray=np.asarray(body,dtype=np.float32)
    residual=gray-np.asarray(body.filter(ImageFilter.GaussianBlur(15)),dtype=np.float32)
    mask=residual>20;h,w=mask.shape;components=[]
    coords=np.where(mask);stats['foreground_pixels']=len(coords[0])
    if expired():return abort('deadline_after_mask')
    if len(coords[0])>max_foreground:return abort('foreground_limit')
    for yy,xx in zip(*coords):
        if not mask[yy,xx]:continue
        stats['components_discovered']+=1
        if stats['components_discovered']>max_components:return abort('component_limit')
        if expired():return abort('deadline_inside_components')
        todo=[(int(yy),int(xx))];mask[yy,xx]=False;n=0;xlo=xhi=int(xx);ylo=yhi=int(yy)
        while todo:
            y,x=todo.pop();n+=1;stats['visited_pixels']+=1
            if stats['visited_pixels']%256==0 and expired():return abort('deadline_inside_bfs')
            xlo=min(xlo,x);xhi=max(xhi,x);ylo=min(ylo,y);yhi=max(yhi,y)
            for dy,dx in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                qy,qx=y+dy,x+dx
                if 0<=qy<h and 0<=qx<w and mask[qy,qx]:
                    mask[qy,qx]=False;todo.append((qy,qx))
        if n>=10 and yhi-ylo>=7 and xhi-xlo>=2:
            components.append([xlo,ylo,xhi+1,yhi+1])
    boxes=[b for b in components if b[2]-b[0]<=w*.9 and b[3]-b[1]<=h*.3]
    changed=True
    while changed:
        changed=False
        for i,b in enumerate(boxes):
            for j in range(i):
                stats['merge_pairs']+=1
                if stats['merge_pairs']>max_pairs:return abort('merge_pair_limit')
                if stats['merge_pairs']%256==0 and expired():return abort('deadline_inside_merge')
                q=boxes[j];bh=b[3]-b[1];qh=q[3]-q[1]
                overlap=max(0,min(b[3],q[3])-max(b[1],q[1]))
                gap=max(0,max(b[0],q[0])-min(b[2],q[2]))
                if overlap>=.5*min(bh,qh) and gap<=.7*max(bh,qh):
                    boxes[j]=[min(b[0],q[0]),min(b[1],q[1]),max(b[2],q[2]),max(b[3],q[3])]
                    boxes.pop(i);changed=True;break
            if changed:break
    boxes=[b for b in boxes if b[2]-b[0]>=15 and (b[2]-b[0])/(b[3]-b[1])>=1.5]
    if expired():return abort('deadline_after_merge')
    return sorted(boxes,key=lambda b:(-(b[2]-b[0])*(b[3]-b[1]),b[1],b[0],b[3],b[2]))[:limit],stats

def extract_character_evidence(image, box, assets, catalog, candidate_indices=None,
                               budget_ms=550, max_calls=4):
    """Return literal observations and separately trusted semantic fields.

    Call only after ordinary word OCR leaves variant ambiguity unresolved.
    If candidate_indices is supplied, accepted fields require known metadata in
    that shortlist. Otherwise the caller must constrain global semantic evidence
    to its related original Top5 family before making a retrieval decision.
    """
    start=time.perf_counter();deadline=start+budget_ms/1000
    x1,y1,x2,y2=box;bw,bh=x2-x1,y2-y1
    body_box=[max(0,math.floor(x1+.06*bw)),max(0,math.floor(y1+.30*bh)),
              min(image.width,math.ceil(x1+.94*bw)),min(image.height,y2)]
    candidates=None if candidate_indices is None else list(map(int,candidate_indices))
    body=image.crop(body_box).convert('L')
    body_scale=min(1,512/body.width,1600/body.height)
    if body_scale<1:
        body=body.resize((round(body.width*body_scale),round(body.height*body_scale)),Image.Resampling.LANCZOS)
    body_scale_x=body.width/(body_box[2]-body_box[0])
    body_scale_y=body.height/(body_box[3]-body_box[1])
    lexicon=grape_alias_lexicon(catalog)
    proposal_started=time.perf_counter()
    proposals,proposal_stats=word_proposals(body,min(4,max_calls),deadline)
    proposal_stats['wall_ms']=1000*(time.perf_counter()-proposal_started)
    observations=[];errors=[];matches=[]
    known=set(catalog.vocab) if candidates is None else set().union(*(catalog.rows[i]['grape'] for i in candidates))
    exhausted=bool(proposal_stats['aborted'] and proposal_stats['abort_reason'].startswith('deadline'))
    attempts=0
    for n,b in enumerate(proposals):
        remaining=deadline-time.perf_counter()
        if remaining<=0:exhausted=True;break
        crop=[max(0,b[0]-5),max(0,b[1]-5),min(body.width,b[2]+5),min(body.height,b[3]+5)]
        raw=body.crop(crop);roi=ImageOps.invert(ImageOps.autocontrast(raw,cutoff=.5))
        roi=roi.resize((roi.width*3,roi.height*3),Image.Resampling.LANCZOS)
        roi=ImageOps.expand(roi,border=20,fill=255);stream=io.BytesIO();roi.save(stream,format='PNG')
        remaining=deadline-time.perf_counter()
        if remaining<=0:exhausted=True;break
        env=dict(os.environ,TESSDATA_PREFIX=assets['tessdata_dir'],OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
        attempts+=1;step=time.perf_counter()
        try:
            process=subprocess.run([assets['tesseract'],'stdin','stdout','-l','eng','--psm','8',
                                    '-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1'],
                                    input=stream.getvalue(),capture_output=True,timeout=remaining,env=env)
            if process.returncode:raise ValueError('Tesseract process failed')
            hocr=process.stdout.decode();parser=Hocr();parser.feed(hocr)
        except Exception as exc:
            errors.append({'proposal':n,'type':type(exc).__name__});
            if isinstance(exc,subprocess.TimeoutExpired):exhausted=True;break
            continue
        words=[]
        for word in parser.words:
            literal=''.join(c['char'] for c in word['chars'])
            accepted=global_unique_fragments(word['chars'],lexicon)
            # Keep raw hOCR and OCR-coordinate rectangles; additionally map each
            # rectangle through scale/border/crop transforms into input pixels.
            for char in word['chars']:
                rect=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',char['title'])
                if rect:
                    xa,ya,xb,yb=map(int,rect.groups())
                    char['input_box']=[body_box[0]+(crop[0]+(xa-20)/3)/body_scale_x,
                                       body_box[1]+(crop[1]+(ya-20)/3)/body_scale_y,
                                       body_box[0]+(crop[0]+(xb-20)/3)/body_scale_x,
                                       body_box[1]+(crop[1]+(yb-20)/3)/body_scale_y]
            for match in accepted:
                match.update(literal=literal,proposal=n,canonical=match['grape'],
                             charboxes=word['chars'],
                             coords=[body_box[0]+crop[0]/body_scale_x,body_box[1]+crop[1]/body_scale_y,
                                     body_box[0]+crop[2]/body_scale_x,body_box[1]+crop[3]/body_scale_y],
                             reason='maximal_high_confidence_character_run_exact_unique_global_alias')
                matches.append(match)
            words.append(dict(word,literal=literal,fragment_matches=accepted))
        observations.append({'proposal':n,'body_word_box':b,
                             'input_roi':[body_box[0]+crop[0]/body_scale_x,body_box[1]+crop[1]/body_scale_y,body_box[0]+crop[2]/body_scale_x,body_box[1]+crop[3]/body_scale_y],
                             'transform':{'scale':3,'border':20,'body_scale_x':body_scale_x,'body_scale_y':body_scale_y},'words':words,'hocr':hocr,
                             'wall_ms':1000*(time.perf_counter()-step)})
    grapes={m['grape'] for m in matches}
    accepted=sorted(grapes) if len(grapes)==1 and grapes<=known else []
    reason=('proposal_computation_aborted' if proposal_stats['aborted'] else
            'unique_global_grape_fragment_in_visual_family' if accepted else
            'contradictory_character_grapes' if len(grapes)>1 else
            'metadata_unknown_or_outside_visual_family' if grapes else 'no_reliable_character_fragment')
    return {'version':VERSION,'accepted_fields':{'grape':accepted},'reason':reason,
            'character_matches':matches,'observations':observations,'errors':errors,
            'proposal_budget':proposal_stats,
            'body_box':body_box,'proposals':proposals,'candidate_indices':candidates,
            'budget_ms':budget_ms,'max_calls':min(4,max_calls),'calls_attempted':attempts,
            'calls_completed':len(observations),'budget_exhausted':exhausted,
            'partial_observations':len(observations)<len(proposals),
            'wall_ms':1000*(time.perf_counter()-start),'confidence_type':'hocr_character_not_word'}

def acquire(image,box,assets,catalog_vocab):
    """Root integration API: global literal semantic evidence, no row selection."""
    class Vocabulary:
        vocab=set(catalog_vocab)
    result=extract_character_evidence(image,box,assets,Vocabulary())
    result['accepted_grapes']=result['accepted_fields']['grape']
    result['evidence']=result['character_matches']
    return result
