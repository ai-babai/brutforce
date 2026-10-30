"""Experimental bounded noise-abort reacquisition; never called by frozen C13.
Locations/chromatic contrast nominate; genuine word90/char90 proves fields.
"""
import csv,io,math,os,re,subprocess,tempfile,time
from pathlib import Path
from PIL import Image,ImageOps
from character_acquisition import Hocr
from local_grape_acquisition import physical_row
from baseline_rectification import rectify,inverse_box
from title_evidence import verify_word as character90
from tsv_word_evidence import parse as parse_TSV
from field_contract import core_token,word90,KEYS
from chromatic_row import project
from ink_rows import propose as ink_rows
VERSION='resource-abort-complete-fields-v2-fresh-dual-location-word90-unvalidated'
BUDGET_MS=1500;MAX_CALLS=4
def ocr_options(psm):return ['-c','tessedit_create_tsv=1','-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1']
def sufficient_fields(fields):return bool(fields['grape'] or (fields['color'] and fields['product']))

def acquire(image,box,assets,lexicon,budget_ms=BUDGET_MS,max_calls=MAX_CALLS):
    start=time.perf_counter();deadline=start+min(BUDGET_MS,budget_ms)/1000;cap=min(MAX_CALLS,max_calls);calls=[];errors=[];evidence=[];accepted={k:set() for k in KEYS};exhausted=False
    x1,y1,x2,y2=box
    if not (0<=x1<x2<=image.width and 0<=y1<y2<=image.height):raise ValueError('Selected bottle coordinates invalid')
    # Full independently selected bottle, no fixed upper/lower label layout.
    source=[math.floor(x1),math.floor(y1),math.ceil(x2),math.ceil(y2)];body=image.crop(source).convert('RGB');env=dict(os.environ,TESSDATA_PREFIX=assets['tessdata_dir'],OMP_NUM_THREADS='1',OMP_THREAD_LIMIT='1')
    def call(roi,method,psm,source_box,transform,group):
        nonlocal exhausted
        remaining=deadline-time.perf_counter()
        if remaining<=0 or len(calls)>=cap:exhausted=True;return None
        b=io.BytesIO();roi.save(b,format='PNG');remaining=deadline-time.perf_counter()
        if remaining<=0:exhausted=True;return None
        c={'index':len(calls),'method':method,'language':'rus+eng','psm':psm,'source_box':source_box,'transform':transform,'correlation_group':group,'timeout_ms':1000*remaining,'errors':[]};calls.append(c);t=time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix='noise-field-dual-') as directory:
                output=str(Path(directory)/'ocr');options=ocr_options(psm)
                p=subprocess.run([assets['tesseract'],'stdin',output,'-l','rus+eng','--psm',str(psm)]+options,input=b.getvalue(),capture_output=True,timeout=remaining,env=env)
                if p.returncode:raise RuntimeError('Tesseract exit '+str(p.returncode))
                raw=Path(output+'.tsv').read_text();c['raw_TSV']=raw;c['TSV_words']=parse_TSV(raw)
                c['raw_hOCR']=Path(output+'.hocr').read_text()
            return c
        except Exception as exc:
            error={'call':c['index'],'type':type(exc).__name__,'message':str(exc)[:160]};errors.append(error);c['errors'].append(error)
            if isinstance(exc,subprocess.TimeoutExpired):exhausted=True
            return None
        finally:c['wall_ms']=1000*(time.perf_counter()-t)
    location,channel=project(body);scale=min(2.,1800/max(body.size));location=location.resize((max(1,round(body.width*scale)),max(1,round(body.height*scale))),Image.Resampling.LANCZOS);sx=location.width/body.width;sy=location.height/body.height
    c=call(location,'chromatic_location_only',11,source,{'scale_x':sx,'scale_y':sy,'chromatic_projection':channel},'selected-whole-bottle');words=[]
    if c:
        for w in c['TSV_words']:
            a,b,d,e=w['box'];words.append(dict(w,box=[a/sx,b/sy,d/sx,e/sy]))
    proposals=[]
    for word in words:
        token=core_token(word['text'])
        if word['confidence']<60 or token not in lexicon:continue
        row=physical_row(word,words,body.size)
        if any(max(0,min(row['box'][3],q['box'][3])-max(row['box'][1],q['box'][1]))>=.5*min(row['box'][3]-row['box'][1],q['box'][3]-q['box'][1]) for q in proposals):continue
        proposals.append(dict(row,anchor=word,raw_location_only=True))
    proposals=sorted(proposals,key=lambda r:(r['box'][1],r['box'][0]))[:2]
    ink_proof=None
    if len(proposals)<2:
        bw,bh=body.size;trim=[math.floor(.06*bw),math.floor(.30*bh),math.ceil(.94*bw),bh]
        blind,ink_proof=ink_rows(body.crop(trim),deadline=deadline,max_rows=2)
        ink_proof['existing_body_geometry_trim']=trim
        for row in blind:
            b=row['box'];row['box']=[b[0]+trim[0],b[1]+trim[1],b[2]+trim[0],b[3]+trim[1]]
        for row in blind:
            b=row['box']
            if not any(max(0,min(b[3],q['box'][3])-max(b[1],q['box'][1]))>=.5*min(b[3]-b[1],q['box'][3]-q['box'][1]) for q in proposals):proposals.append(row)
        proposals=proposals[:2]
    pending=[]
    def consume(call_result,roi,source_box,transform,rectification=None):
        parser=Hocr();parser.feed(call_result['raw_hOCR']);eligible=[]
        for word in parser.words:
            genuine=word90(word,call_result['TSV_words'],roi.size,lexicon);chars=character90(word,roi,set(lexicon),word_confidence=None);token=core_token(genuine['literal']);matches=lexicon.get(token,set())
            accepted_char=chars.get('accepted') and len(matches)==1
            item={'literal':genuine['literal'],'actual_word90_proof':genuine,'character90_geometry_proof':chars,'source_box':source_box,'source_transform':transform,'physical_source_group':call_result['correlation_group'],'rectification':rectification,'accepted':bool(genuine['accepted'] or accepted_char),'call':call_result['index']}
            if item['accepted']:
                key,value=(genuine['key'],genuine['value']) if genuine['accepted'] else next(iter(matches));item.update(key=key,value=value,confidence_type='actual_TSV_word90' if genuine['accepted'] else 'unchanged_character90_geometry');accepted[key].add(value)
            for ch in chars.get('chars',[]):
                b=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',ch.get('title',''))
                if b:
                    raw=list(map(int,b.groups()));mapped=inverse_box(raw,rectification) if rectification is not None else raw;xa,ya,xb,yb=mapped
                    ch['text_canvas_box']=[source_box[0]+(xa-transform['border'])/transform['scale_x'],source_box[1]+(ya-transform['border'])/transform['scale_y'],source_box[0]+(xb-transform['border'])/transform['scale_x'],source_box[1]+(yb-transform['border'])/transform['scale_y']]
                    ch['nonlinear_enclosure']=rectification is not None
            evidence.append(item)
            if not item['accepted'] and token in lexicon and chars.get('reason') in ('collapsed_or_merged_glyph','excessive_overlap','disconnected_glyph_sequence'):
                confidences=[re.search(r'x_conf ([0-9.]+)',x.get('title','')) for x in chars.get('core_chars',[])]
                if confidences and all(x and float(x[1])>=90 for x in confidences):eligible.append(word)
        return eligible
    # Fresh SAME firstprocess dual output may itself have genuine word90;
    # old v1 raw-only location receipts are never retroactively promoted.
    if c is not None:consume(c,location,source,{'scale_x':sx,'scale_y':sy,'border':0,'chromatic_projection':channel})
    # Cover distinct physical rows before correlated reprocessing; max2 rows.
    for row in proposals:
        if exhausted or sufficient_fields(accepted):break
        b=row['box'];rgb=body.crop(b);gray,ch=project(rgb);s=min(3.,max(1.,72/gray.height));gray=gray.resize((max(1,round(gray.width*s)),max(1,round(gray.height*s))),Image.Resampling.LANCZOS);transform={'scale_x':gray.width/(b[2]-b[0]),'scale_y':gray.height/(b[3]-b[1]),'border':16,'chromatic_projection':ch};roi=ImageOps.expand(gray,border=16,fill=255);sb=[source[0]+b[0],source[1]+b[1],source[0]+b[2],source[1]+b[3]];group='selected-bottle-physical-row:'+','.join(map(str,sb[1::2]));c=call(roi,'full_row_chromatic',7,sb,transform,group)
        if c:
            eligible=consume(c,roi,sb,transform)
            if eligible:pending.append((roi,eligible[0],sb,transform,group))
    if pending and not exhausted and not sufficient_fields(accepted) and len(calls)<cap:
        roi,word,sb,transform,group=pending[0];warped,proof=rectify(roi,word,deadline=deadline)
        if warped is not None:
            c=call(warped,'physical_baseline_rectified',7,sb,dict(transform,rectification=proof),group)
            if c:consume(c,warped,sb,transform,rectification=proof)
    elapsed=1000*(time.perf_counter()-start);conflict=any(len(v)>1 for v in accepted.values());fields={k:sorted(v) if not conflict else [] for k,v in accepted.items()}
    return {'version':VERSION,'accepted_fields':fields,'evidence':evidence,'calls':calls,'errors':errors,'proposals':proposals,'independent_ink_row_proposal':ink_proof,'source_bottle_box':source,'coordinate_space':'supplied_text_canvas_pixel_edges','reason':'conflicting_fields_abstain' if conflict else 'bounded_complete_field_acquisition','budget':{'limit_ms':min(BUDGET_MS,budget_ms),'max_calls':cap,'calls_attempted':len(calls),'calls_completed':sum(not c['errors'] for c in calls),'exhausted':bool(exhausted or elapsed>min(BUDGET_MS,budget_ms)),'returned_wall_ms':elapsed,'drained_wall_ms':elapsed,'synchronous_drained':True},'correlation_contract':'samephysicalrow RGB projections/rectification are correlated; no80 vote manufacture','product_is_grape':False}
