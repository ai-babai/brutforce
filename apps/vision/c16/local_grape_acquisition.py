"""Additive bounded bilingual whole-grape reacquisition; no default ranking.
Caller must preserve original C09 and gate unresolved/no-prior-override queries.
"""
import csv,io,math,os,re,subprocess,time,unicodedata,tempfile,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter,ImageOps
from candidate_policy import canonical_norm
from character_acquisition import Hocr,grape_alias_lexicon
from semantic_evidence import complete_descriptor
from unicode_grape_evidence import verify
from baseline_rectification import rectify,inverse_box
from tsv_word_evidence import parse as parse_TSV,verify as verify_TSV
VERSION='local-whole-grape-bilingual-v5-word90-budget900'
BUDGET_MS=900
MAX_CALLS=4

def alias_map(vocab):
    class Vocabulary:pass
    Vocabulary.vocab=set(vocab)
    result={}
    for alias,values in grape_alias_lexicon(Vocabulary()).items():
        token=canonical_norm(alias)
        if len(token.split())==1:result.setdefault(token,set()).update(values)
    return result

def physical_row(anchor,words,body_size):
    """TSV locations nominate physical coverage, never semantic confidence.
    Include connected similarly sized/aligned words regardless of OCR confidence;
    stop symmetric padding at nearby other rows without cutting the source row.
    Overlapping neighbor boxes are retained as uncertainty, not trusted evidence.
    """
    w,h=body_size;ab=anchor['box'];ah=ab[3]-ab[1]
    valid=[x for x in words if len(x.get('box',[]))==4 and
           0<=x['box'][0]<x['box'][2]<=w and 0<=x['box'][1]<x['box'][3]<=h]
    row=[anchor];remaining=[x for x in valid if x is not anchor]
    while True:
        left=min(x['box'][0] for x in row);right=max(x['box'][2] for x in row)
        additions=[]
        for x in remaining:
            b=x['box'];height=b[3]-b[1]
            overlap=max(0,min(ab[3],b[3])-max(ab[1],b[1]))
            aligned=(.5*ah<=height<=2*ah and overlap>=.5*min(ah,height)
                     and abs((b[1]+b[3]-ab[1]-ab[3])/2)<=.35*max(ah,height))
            gap=max(0,left-b[2],b[0]-right)
            if aligned and gap<=2*ah:additions.append(x)
        if not additions:break
        row.extend(additions);remaining=[x for x in remaining if all(x is not a for a in additions)]
    rb=[min(x['box'][0] for x in row),min(x['box'][1] for x in row),
        max(x['box'][2] for x in row),max(x['box'][3] for x in row)]
    rh=rb[3]-rb[1];left=max(0,rb[0]-.5*rh);right=min(w,rb[2]+.5*rh)
    top=max(0,rb[1]-.5*rh);bottom=min(h,rb[3]+.5*rh);neighbors=[]
    cy=(rb[1]+rb[3])/2
    for x in remaining:
        b=x['box']
        if min(right,b[2])<=max(left,b[0]):continue
        ny=(b[1]+b[3])/2
        if ny<cy:
            boundary=(b[3]+rb[1])/2 if b[3]<=rb[1] else rb[1]
            if boundary>top:
                top=boundary;neighbors.append({'side':'above','word':x,'boundary':boundary,'overlap':b[3]>rb[1]})
        elif ny>cy:
            boundary=(rb[3]+b[1])/2 if b[1]>=rb[3] else rb[3]
            if boundary<bottom:
                bottom=boundary;neighbors.append({'side':'below','word':x,'boundary':boundary,'overlap':b[1]<rb[3]})
    box=[math.floor(left),math.floor(top),math.ceil(right),math.ceil(bottom)]
    return {'box':box,'row_words':row,'unclipped_word_union':rb,'neighbor_stops':neighbors,
            'row_coverage_contract':'entire connected same-baseline TSV word union; symmetric half-row-height context; nearest other-row boundary',
            'neighbor_overlap_is_uncertainty':any(x['overlap'] for x in neighbors)}

def proposals(words,body_size,lexicon):
    """Location confidence nominates only; entire exact token, no fuzzy suffix."""
    w,h=body_size;found=[]
    for x in words:
        text=x['text'];lo=0;hi=len(text)
        while lo<hi and unicodedata.category(text[lo]).startswith('P'):lo+=1
        while hi>lo and unicodedata.category(text[hi-1]).startswith('P'):hi-=1
        core=text[lo:hi]
        if not core.isalpha() or len(core)<5 or x['confidence']<60:continue
        token=canonical_norm(core)
        role='grape_location' if token in lexicon else ('descriptor_location' if complete_descriptor(core) else None)
        if role is None:continue
        x1,y1,x2,y2=x['box'];height=y2-y1
        if not (0<=x1<x2<=w and 0<=y1<y2<=h) or height<=0:continue
        geometry=physical_row(x,words,body_size)
        found.append(dict(geometry,anchor=x,nomination_role=role,raw_confidence_is_location_only=True))
    ordered=sorted(found,key=lambda x:(x['nomination_role']!='grape_location',x['box'][1],x['anchor']['box'][0]))
    unique=[]
    for p in ordered:
        b=p['box']
        if any(max(0,min(b[3],q['box'][3])-max(b[1],q['box'][1]))>=.5*min(b[3]-b[1],q['box'][3]-q['box'][1]) for q in unique):continue
        unique.append(p)
    return unique[:2]

def acquire(image,box,assets,catalog_vocab,budget_ms=BUDGET_MS,max_calls=MAX_CALLS):
    start=time.perf_counter();deadline=start+min(BUDGET_MS,budget_ms)/1000;max_calls=min(MAX_CALLS,max_calls)
    x1,y1,x2,y2=box;bw,bh=x2-x1,y2-y1
    body_box=[max(0,math.floor(x1+.06*bw)),max(0,math.floor(y1+.30*bh)),min(image.width,math.ceil(x1+.94*bw)),min(image.height,math.ceil(y2))]
    body=image.crop(body_box).convert('L');calls=[];errors=[];observations=[];accepted=set();exhausted=False
    lexicon=alias_map(catalog_vocab)
    env=dict(os.environ,TESSDATA_PREFIX=assets['tessdata_dir'],OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
    def call(roi,kind,psm,source,transform,group):
        nonlocal exhausted
        remaining=deadline-time.perf_counter()
        if remaining<=0 or len(calls)>=max_calls:exhausted=True;return None
        stream=io.BytesIO();roi.save(stream,format='PNG');remaining=deadline-time.perf_counter()
        if remaining<=0:exhausted=True;return None
        record={'index':len(calls),'method':kind,'language':'rus+eng','psm':psm,'source_box':source,'coordinate_space':'supplied_text_canvas_pixel_edges','transform':transform,'correlation_group':group,'timeout_ms':remaining*1000,'errors':[]};calls.append(record);t=time.perf_counter()
        options=['-c','tessedit_create_tsv=1'] if kind=='location_tsv' else ['-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1']
        try:
            if kind=='location_tsv':
                p=subprocess.run([assets['tesseract'],'stdin','stdout','-l','rus+eng','--psm',str(psm)]+options,input=stream.getvalue(),capture_output=True,timeout=remaining,env=env)
                if p.returncode:raise RuntimeError('Tesseract nonzero exit '+str(p.returncode))
                literal=p.stdout.decode()
            else:
                # One process, two real renderers: TSV float is never inferred
                # from the hOCR renderer's rounded integer confidence.
                with tempfile.TemporaryDirectory(prefix='local-grape-dual-') as directory:
                    basename=str(Path(directory)/'ocr')
                    p=subprocess.run([assets['tesseract'],'stdin',basename,'-l','rus+eng','--psm',str(psm)]+options+['-c','tessedit_create_tsv=1'],input=stream.getvalue(),capture_output=True,timeout=remaining,env=env)
                    if p.returncode:raise RuntimeError('Tesseract nonzero exit '+str(p.returncode))
                    literal=Path(basename+'.hocr').read_text()
                    raw_TSV=Path(basename+'.tsv').read_text()
                record['raw_TSV_output']=raw_TSV;record['raw_TSV_sha256']=hashlib.sha256(raw_TSV.encode()).hexdigest()
                record['same_process_actual_TSV_words']=parse_TSV(raw_TSV)
            record['raw_output']=literal
            if not literal.strip():raise ValueError('empty OCR output')
            return literal
        except Exception as exc:
            e={'call':record['index'],'type':type(exc).__name__,'message':str(exc)[:200]};errors.append(e);record['errors'].append(e)
            if isinstance(exc,subprocess.TimeoutExpired):exhausted=True
            return None
        finally:record['wall_ms']=1000*(time.perf_counter()-t)
    scale=min(2.,1800/max(body.size));location=ImageOps.autocontrast(body).resize((max(1,round(body.width*scale)),max(1,round(body.height*scale))),Image.Resampling.LANCZOS)
    sx=location.width/body.width;sy=location.height/body.height
    raw=call(location,'location_tsv',11,body_box,{'scale_x':sx,'scale_y':sy,'border':0},'selected-bottle-body')
    words=[]
    if raw:
        try:
            for r in csv.DictReader(io.StringIO(raw),delimiter='\t',quoting=csv.QUOTE_NONE):
                if r.get('level')=='5' and r.get('text','').strip():
                    x,y,w,h=[int(r[k]) for k in ['left','top','width','height']]
                    words.append({'text':r['text'],'confidence':float(r['conf']),'box':[x/sx,y/sy,(x+w)/sx,(y+h)/sy]})
            calls[-1]['words']=words
        except Exception as exc:errors.append({'call':0,'type':type(exc).__name__,'message':'Invalid location TSV '+str(exc)[:150]})
    rows=proposals(words,body.size,lexicon)
    for n,proposal in enumerate(rows):
        if accepted or exhausted:break
        b=proposal['box'];source=[body_box[0]+b[0],body_box[1]+b[1],body_box[0]+b[2],body_box[1]+b[3]]
        group='selected-bottle-physical-row:'+','.join(map(str,source[1::2]))
        gray=body.crop(b);s=min(3.,max(1.,72/gray.height));gray=gray.resize((max(1,round(gray.width*s)),max(1,round(gray.height*s))),Image.Resampling.LANCZOS)
        scale_x=gray.width/(b[2]-b[0]);scale_y=gray.height/(b[3]-b[1]);bright=np.median(np.asarray(gray))<128
        a=np.asarray(gray,dtype=np.float32);bg=np.asarray(gray.filter(ImageFilter.GaussianBlur(9)),dtype=np.float32);mask=(a-bg>8) if bright else (a-bg< -8)
        contrast=ImageOps.autocontrast(gray);contrast=ImageOps.invert(contrast) if bright else contrast
        variants=[('line_autocontrast',contrast),('line_local_foreground',ImageOps.invert(Image.fromarray(np.uint8(mask)*255)))]
        rectification_attempted=False
        def consume(text,roi,rectification=None):
            parser=Hocr();eligible=[]
            try:parser.feed(text)
            except Exception as exc:
                errors.append({'call':len(calls)-1,'type':type(exc).__name__,'message':'Invalid hOCR'});return eligible
            current=[]
            for word in parser.words:
                match=re.search(r'x_wconf ([0-9.]+)',word.get('title',''));word_conf=float(match[1]) if match else None
                TSV_proof=verify_TSV(word,calls[-1].get('same_process_actual_TSV_words',[]),roi.size,lexicon)
                actual_confidence=TSV_proof.get('actual_TSV_word',{}).get('confidence')
                item=verify(word,roi,catalog_vocab,word_confidence=None)
                item['character_geometry_result']={k:item.get(k) for k in ('accepted','reason','geometry_version')}
                item['actual_word90_proof']=TSV_proof
                if TSV_proof['accepted']:
                    item.update(accepted=True,accepted_grapes=TSV_proof['accepted_grapes'],reason=TSV_proof['reason'],confidence_type='actual_TSV_float_word90')
                item.update(raw_word_confidence=word_conf,call_index=len(calls)-1,physical_source_group=group,source_box=source,coordinate_space='supplied_text_canvas_pixel_edges')
                if rectification is not None:item['rectification']=rectification
                for char in item.get('chars',[]):
                    z=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',char.get('title',''))
                    if z:
                        raw_box=list(map(int,z.groups()));mapped=inverse_box(raw_box,rectification) if rectification is not None else raw_box
                        xa,ya,xb,yb=mapped
                        char['text_canvas_box']=[source[0]+(xa-16)/scale_x,source[1]+(ya-16)/scale_y,source[0]+(xb-16)/scale_x,source[1]+(yb-16)/scale_y]
                        if rectification is not None:char['mapped_box_is_conservative_nonlinear_enclosure']=True
                observations.append(item);current.append(item)
                if item['accepted']:accepted.update(item['accepted_grapes'])
                if rectification is None and item.get('reason') in ('collapsed_or_merged_glyph','excessive_overlap','disconnected_glyph_sequence'):
                    chars=item.get('core_chars',[]);core=item.get('alphabetic_core','')
                    high=[]
                    for ch in chars:
                        q=re.search(r'x_conf ([0-9.]+)',ch.get('title',''));high.append(q is not None and float(q[1])>=90)
                    if core.isalpha() and len(core)>=5 and canonical_norm(core) in lexicon and all(high) and high:eligible.append(word)
            calls[-1]['observations']=current
            return eligible
        for method,roi in variants:
            if accepted or exhausted:break
            roi=ImageOps.expand(roi,border=16,fill=255)
            transform={'scale_x':scale_x,'scale_y':scale_y,'border':16}
            text=call(roi,method,7,source,transform,group)
            if text is None:continue
            eligible=consume(text,roi)
            # One deterministic reOCR per physical row; it yields new genuine
            # confidence/geometry, never substitutes observed boxes for hOCR.
            if not accepted and eligible and not rectification_attempted:
                rectification_attempted=True
                warped,proof=rectify(roi,eligible[0],deadline=deadline)
                calls[-1]['baseline_rectification_proposal']=proof
                if warped is not None:
                    text=call(warped,'line_baseline_rectified',7,source,dict(transform,rectification=proof),group)
                    if text is not None:consume(text,warped,rectification=proof)
    wall=1000*(time.perf_counter()-start)
    # No reliable query if observations yield conflicting actual varietal fields.
    trusted=sorted(accepted) if len(accepted)==1 else []
    return {'version':VERSION,'accepted_fields':{'grape':trusted},'accepted_grapes':trusted,'evidence':observations,'calls':calls,'errors':errors,'proposals':rows,'body_box':body_box,
      'budget':{'limit_ms':min(BUDGET_MS,budget_ms),'max_calls':max_calls,'calls_attempted':len(calls),'calls_completed':sum(not c['errors'] for c in calls),'exhausted':bool(exhausted or wall>min(BUDGET_MS,budget_ms)),'returned_wall_ms':wall,'drained_wall_ms':wall,'synchronous_drained':True},
      'reason':'unique_complete_grape_token' if trusted else ('contradictory_grape_evidence' if len(accepted)>1 else 'no_reliable_complete_grape_token'),
      'correlation_contract':'same physical row transforms; no independent word80votes','coordinate_space':'supplied_text_canvas_pixel_edges'}
