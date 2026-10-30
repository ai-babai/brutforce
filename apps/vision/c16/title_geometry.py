"""Full-image component text rows; one bounded physical following-title role."""
import io,math,os,re,subprocess,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter,ImageOps
from semantic_acquisition import Hocr
from title_evidence import verify_word
from candidate_policy import canonical_norm
from gram_ocr import attributes
VERSION='full-label-component-title-row-v3-bilingual-query'
MAX_CALLS=4;BUDGET_MS=550;MAX_PIXELS=50000

def components_and_rows(image,deadline):
    scale=min(1,320/max(image.size));im=image.convert('L').resize((round(image.width*scale),round(image.height*scale)));a=np.asarray(im,dtype=float);bg=np.asarray(im.filter(ImageFilter.GaussianBlur(5)),dtype=float)
    rows=[];all_components=[];visited=0
    for polarity,mask in [('dark',(a-bg)<-8),('light',(a-bg)>8)]:
        comp=[];padding_components=[];remaining=mask.copy()
        for yy,xx in np.argwhere(mask):
            if time.perf_counter()>=deadline:raise TimeoutError('geometry deadline')
            if not remaining[yy,xx]:continue
            todo=[(int(yy),int(xx))];remaining[yy,xx]=False;minx=maxx=int(xx);miny=maxy=int(yy);area=0
            while todo:
                y,x=todo.pop();visited+=1;area+=1;minx=min(x,minx);maxx=max(x,maxx);miny=min(y,miny);maxy=max(y,maxy)
                if visited%128==0 and (visited>MAX_PIXELS or time.perf_counter()>=deadline):raise TimeoutError('geometry pixel/deadline bound')
                for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                    ny,nx=y+dy,x+dx
                    if 0<=ny<mask.shape[0] and 0<=nx<mask.shape[1] and remaining[ny,nx]:remaining[ny,nx]=False;todo.append((ny,nx))
            w=maxx-minx+1;h=maxy-miny+1
            # Border stops retain even tiny ink components; these are only
            # acquisition boundaries, never lexical/semantic evidence.
            if 1<=h<=im.height/4 and 1<=w<=im.width/3:
                padding_components.append([minx/scale,miny/scale,(maxx+1)/scale,(maxy+1)/scale])
            if area>=3 and 5<=h<=im.height/4 and 1<=w<=im.width/3 and .03<=area/(w*h)<=.85:comp.append([minx,miny,maxx+1,maxy+1])
        groups=[]
        for c in sorted(comp,key=lambda c:(c[3],c[0])):
            if time.perf_counter()>=deadline:raise TimeoutError('row grouping deadline')
            h=c[3]-c[1];matched=[]
            for n,g in enumerate(groups):
                mh=float(np.median([z[3]-z[1] for z in g]));bottom=float(np.median([z[3] for z in g]))
                if abs(c[3]-bottom)<=.3*max(h,mh) and .5<=h/mh<=2:matched.append(n)
            if matched:groups[matched[-1]].append(c)
            else:groups.append([c])
        original=[[v/scale for v in c] for c in comp];all_components.extend(original)
        for group in groups:
            group=sorted(group,key=lambda c:c[0]);mh=float(np.median([c[3]-c[1] for c in group]));runs=[]
            for c in group:
                if runs and c[0]-runs[-1][-1][2]<=2*mh:runs[-1].append(c)
                else:runs.append([c])
            for run in runs:
                if len(run)<4:continue
                b=[min(c[0] for c in run),min(c[1] for c in run),max(c[2] for c in run),max(c[3] for c in run)]
                if (b[2]-b[0])/(b[3]-b[1])<2:continue
                rows.append({'box':[v/scale for v in b],'components':[[v/scale for v in c] for c in run],'all_components':original,'padding_components':padding_components,'median_height':mh/scale,'priority':mh*(b[2]-b[0]),'polarity':polarity})
    selected=[]
    for row in sorted(rows,key=lambda r:(sum(max(0,c[2]-z[0]) for c,z in zip(r['components'],r['components'][1:]))/(r['box'][2]-r['box'][0]),-r['priority'],r['box'][1],r['polarity'])):
        b=row['box']
        if any(max(0,min(b[2],r['box'][2])-max(b[0],r['box'][0]))*max(0,min(b[3],r['box'][3])-max(b[1],r['box'][1]))>=.7*min((b[2]-b[0])*(b[3]-b[1]),(r['box'][2]-r['box'][0])*(r['box'][3]-r['box'][1])) for r in selected):continue
        selected.append(row)
    return selected,{'scale':scale,'visited_pixels':visited,'component_count':len(all_components),'proposals':len(selected)}

def padded_box(box,components,image,glyph_height=None):
    h=glyph_height or float(np.median([c[3]-c[1] for c in components]));x1,y1,x2,y2=box
    others=[c for c in components if c[2]>x1 and c[0]<x2]
    above=[c[3] for c in others if c[3]<y1];below=[c[1] for c in others if c[1]>y2]
    top=min(.5*h,(y1-max(above))/2 if above else .5*h);bottom=min(.5*h,(min(below)-y2)/2 if below else .5*h)
    result=[max(0,math.floor(x1-.5*h)),max(0,math.floor(y1-top)),min(image.width,math.ceil(x2+.5*h)),min(image.height,math.ceil(y2+bottom))]
    return result

def following_row(anchor,image,deadline):
    ab=anchor['box'];allc=anchor['all_components'];eligible=[c for c in allc if c[1]>ab[3] and c[1]-ab[3]<2*anchor['median_height'] and c[2]>ab[0]-anchor['median_height'] and c[0]<ab[2]+anchor['median_height']]
    if not eligible:return None,'no_following_ink'
    seed=min(eligible,key=lambda c:(c[1],c[0]));group=[seed];remaining=[c for c in eligible if c!=seed];changed=True
    while changed:
        if time.perf_counter()>=deadline:return None,'row_geometry_deadline'
        changed=False
        for c in remaining[:]:
            for z in group:
                h=c[3]-c[1];zh=z[3]-z[1];overlap=max(0,min(c[3],z[3])-max(c[1],z[1]));gap=max(0,max(c[0],z[0])-min(c[2],z[2]))
                if overlap>=.2*min(h,zh) and gap<=.5*max(h,zh):group.append(c);remaining.remove(c);changed=True;break
    b=[min(c[0] for c in group),min(c[1] for c in group),max(c[2] for c in group),max(c[3] for c in group)]
    # Query/reference role is the complete next connected physical ink row,
    # not arbitrary producer text anywhere in the bottle or an upper logo.
    if len(group)<2 or b[2]-b[0]<=b[3]-b[1]:return None,'not_complete_multi_stroke_following_text_row'
    if any(c[1]>=b[1] and c[3]<=b[3] and c[2]>b[0] and c[0]<b[2] for c in remaining):return None,'ambiguous_uncovered_interior_ink'
    if b[0]<=0 or b[2]>=image.width or b[1]<=0 or b[3]>=image.height:return None,'boundary_cut_row'
    # The anchor span is retained, preventing small disconnected cursive
    # extenders from being silently cropped by downsampled component filtering.
    full=[min(b[0],ab[0]),b[1],max(b[2],ab[2]),b[3]]
    return {'box':padded_box(full,anchor.get('padding_components',allc),image,float(np.median([c[3]-c[1] for c in group]))),'ink_box':b,'components':group,'complete_anchor_span':full,'role':'following_product_title_row'},None

def non_title_row(text,catalog_vocab):
    """Positive acquisition rejection only; never semantic OCR promotion."""
    if any(c.isdigit() for c in text) and not any(c.isalpha() for c in text):return 'numeric_date_vintage_or_measurement_row'
    tokens=canonical_norm(text).split()
    if not tokens:return None
    known=set(' '.join(catalog_vocab).split())
    common={'white','red','rose','dry','sweet','brut','semi','semidry','semisweet'}
    if all(token.isdigit() or token in known or token in common or any(attributes(token)) for token in tokens):return 'only_varietal_or_common_attribute_row'
    return None

def language_plan(script_text,reference_catalog_grapes=None):
    cyr=sum('а'<=c.lower()<='я' or c.lower()=='ё' for c in script_text)
    latin=sum('a'<=c.lower()<='z' for c in script_text)
    if reference_catalog_grapes:
        # Cached references retain their source-bound catalogue localization
        # contract; reference OCR has never established semantic confidence.
        language='rus' if cyr>latin else 'eng';source='reference_catalog_script_prior'
    else:
        # Logos and translated catalogue text cannot establish query script.
        # Cover both installed scripts in one call, with no extra pass/vote.
        language='rus+eng';source='query_installed_bilingual_coverage'
    return {'language':language,'source':source,'observed_cyrillic':cyr,'observed_latin':latin,'same_physical_row_single_pass':True}

def extract(image,assets,catalog_vocab,script_text='',budget_ms=BUDGET_MS,max_calls=MAX_CALLS,reference_catalog_grapes=None):
    start=time.perf_counter();deadline=start+budget_ms/1000;calls=[];errors=[];result={'accepted':False,'version':VERSION,'role':None,'trusted_grapes':[],'catalog_grapes':sorted(reference_catalog_grapes or []),'proof_contract':'reference_catalog_identity_raw_OCR_location' if reference_catalog_grapes else 'query_reliable_whole_grape','calls':calls,'errors':errors}
    plan=language_plan(script_text,reference_catalog_grapes);language=plan['language'];result['language_plan']=plan
    env=dict(os.environ,TESSDATA_PREFIX=assets['tessdata_dir'],OMP_THREAD_LIMIT='1',OMP_NUM_THREADS='1')
    try:
        rows,stats=components_and_rows(image,deadline);result['geometry']=stats
        for row in rows[:2]:
            cs=row['components'];slopes=[(z[3]-c[3])/((z[0]+z[2]-c[0]-c[2])/2) for n,c in enumerate(cs) for z in cs[n+1:] if z[0]+z[2]>c[0]+c[2]];angle=math.degrees(math.atan(float(np.median(slopes)))) if slopes else 0
            if abs(angle)>10:continue
            # Symmetric half-glyph border for OCR; neighbouring cursive strokes
            # must not clip the anchor's own descenders before deskew.
            h=row['median_height']; b=row['box']
            box=[max(0,math.floor(b[0]-.5*h)),max(0,math.floor(b[1]-.5*h)),min(image.width,math.ceil(b[2]+.5*h)),min(image.height,math.ceil(b[3]+.5*h))]
            if box[0]==0 or box[1]==0 or box[2]==image.width or box[3]==image.height:continue
            gray=image.crop(box).convert('L').rotate(angle,Image.Resampling.BICUBIC,expand=True,fillcolor=255);a=np.asarray(gray,dtype=float);bg=np.asarray(gray.filter(ImageFilter.GaussianBlur(9)),dtype=float);mask=(a-bg<-8) if row['polarity']=='dark' else (a-bg>8);ink=ImageOps.invert(Image.fromarray(np.uint8(mask)*255))
            for method,roi in [('local_foreground',ink),('autocontrast',ImageOps.autocontrast(gray))]:
                if len(calls)>=max_calls or time.perf_counter()>=deadline:raise TimeoutError('OCR call/deadline bound')
                stream=io.BytesIO();roi.save(stream,format='PNG');remaining=deadline-time.perf_counter()
                if remaining<=0:raise TimeoutError('OCR serialization deadline')
                record={'index':len(calls),'method':method,'source_box':box,'angle_degrees':angle,'language':language,'correlation_group':'original-physical-row:'+','.join(map(str,row['box'])),'timeout_ms':remaining*1000,'errors':[]};calls.append(record);t=time.perf_counter()
                try:
                    p=subprocess.run([assets['tesseract'],'stdin','stdout','-l',language,'--psm','7','-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1'],input=stream.getvalue(),capture_output=True,timeout=remaining,env=env)
                    if p.returncode:raise RuntimeError('Tesseract nonzero exit')
                    parser=Hocr();parser.feed(p.stdout.decode());evidence=[];trusted=[]
                    for word in parser.words:
                        item=verify_word(word,roi,set(' '.join(catalog_vocab).split()));q=re.search(r'x_wconf ([0-9.]+)',word.get('title',''));confidence=float(q[1]) if q else None;literal=''.join(z.get('char','') for z in word.get('chars',[]));item.update(word_confidence=confidence,raw_word_title=word['title'],raw_chars=word['chars'])
                        # Raw transformed rectangles and their inverse mapping are both
                        # retained; mapped axis-aligned envelopes are observational.
                        mapped=[];theta=math.radians(angle);co=math.cos(theta);si=math.sin(theta)
                        for ch in word['chars']:
                            rect=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',ch.get('title',''))
                            if not rect:continue
                            x1,y1,x2,y2=map(int,rect.groups());points=[]
                            for x,y in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
                                dx=x-roi.width/2;dy=y-roi.height/2;points.append([box[0]+co*dx-si*dy+(box[2]-box[0])/2,box[1]+si*dx+co*dy+(box[3]-box[1])/2])
                            mapped.append({'char':ch.get('char'),'source_envelope':[min(v[0] for v in points),min(v[1] for v in points),max(v[0] for v in points),max(v[1] for v in points)],'raw_title':ch.get('title')})
                        item['original_image_char_rects']=mapped
                        # Reference metadata establishes identity; exact raw whole lexical
                        # tokens nominate location only, never trusted OCR confidence.
                        core=item.get('alphabetic_core','');whole=len(core)>=5 and core.isalpha()
                        if item['accepted']:trusted.append(canonical_norm(core))
                        elif reference_catalog_grapes and whole:trusted.append(canonical_norm(core))
                        elif confidence is not None and confidence>=90:
                            word_proof=verify_word(word,roi,set(' '.join(catalog_vocab).split()),word_confidence=confidence)
                            item['word_geometry_proof']=word_proof
                            if word_proof['accepted']:trusted.append(canonical_norm(core))
                        evidence.append(item)
                    record['evidence']=evidence;record['trusted_tokens']=[] if reference_catalog_grapes else trusted;record['raw_location_tokens']=trusted if reference_catalog_grapes else []
                    value=' '+' '.join(trusted)+' ';grapes={g for g in catalog_vocab if ' '+g+' ' in value};grapes={g for g in grapes if not any(g!=h and ' '+g+' ' in ' '+h+' ' for h in grapes)}
                    if len(grapes)!=1 or reference_catalog_grapes and grapes!=set(reference_catalog_grapes):continue
                    context,reason=following_row(row,image,deadline)
                    result.update(anchor={'source_box':box,'ink_box':row['box'],'angle_degrees':angle,'evidence':evidence,'trusted_tokens':[] if reference_catalog_grapes else trusted,'raw_location_tokens':trusted if reference_catalog_grapes else [],'grapes':sorted(grapes),'proof_contract':result['proof_contract']},trusted_grapes=[] if reference_catalog_grapes else sorted(grapes),following_row=context,reason=reason)
                    if context:
                        # One extra bounded same-row call can reject a positive
                        # non-title observation (vintage/date/descriptors). It
                        # does not demand successful OCR of an unknown cursive
                        # title and cannot fabricate semantic confidence.
                        if len(calls)>=max_calls or time.perf_counter()>=deadline:raise TimeoutError('context role OCR budget')
                        role_roi=ImageOps.autocontrast(image.crop(context['box']).convert('L').rotate(angle,Image.Resampling.BICUBIC,expand=True,fillcolor=255))
                        role_stream=io.BytesIO();role_roi.save(role_stream,format='PNG');role_remaining=deadline-time.perf_counter()
                        if role_remaining<=0:raise TimeoutError('context role serialization budget')
                        role_record={'index':len(calls),'method':'following_row_non_title_rejection','source_box':context['box'],'angle_degrees':angle,'language':language,'correlation_group':'original-following-physical-row:'+','.join(map(str,context['ink_box'])),'timeout_ms':role_remaining*1000,'errors':[],'semantic_promotion':False};calls.append(role_record);role_start=time.perf_counter()
                        try:
                            rp=subprocess.run([assets['tesseract'],'stdin','stdout','-l',language,'--psm','7','-c','tessedit_create_hocr=1','-c','hocr_char_boxes=1'],input=role_stream.getvalue(),capture_output=True,timeout=role_remaining,env=env)
                            if rp.returncode:raise RuntimeError('Tesseract context nonzero exit')
                            role_parser=Hocr();role_parser.feed(rp.stdout.decode());raw_rows=[]
                            for rw in role_parser.words:
                                raw_rows.append({'literal':''.join(c.get('char','') for c in rw['chars']),'raw_word_title':rw['title'],'raw_chars':rw['chars']})
                            raw_line=' '.join(r['literal'] for r in raw_rows);negative=non_title_row(raw_line,catalog_vocab)
                            role_record.update(raw_words=raw_rows,raw_literal=raw_line,positive_non_title_reason=negative)
                            context['role_certification']='following_physical_ink_geometry_no_positive_non_title_OCR'
                            result['role_ocr']=role_record
                            if negative:result['reason']=negative;return result
                        except Exception as exc:
                            role_record['errors'].append(type(exc).__name__);errors.append({'call':role_record['index'],'type':type(exc).__name__});result['reason']='context_role_OCR_failed_abstention';return result
                        finally:role_record['wall_ms']=(time.perf_counter()-role_start)*1000
                        result.update(accepted=True,role=context['role'],box=context['box'],angle_degrees=angle,reason='catalog_identity_exact_raw_grape_location_complete_following_row' if reference_catalog_grapes else 'reliable_whole_grape_complete_following_physical_ink_row');return result
                except Exception as exc:record['errors'].append(type(exc).__name__);errors.append({'call':record['index'],'type':type(exc).__name__})
                finally:record['wall_ms']=(time.perf_counter()-t)*1000
        if not result.get('reason'):result['reason']='mandatory_title_role_budget_unavailable' if any(e['type']=='TimeoutError' for e in errors) else 'no_reliable_whole_grape_anchor_or_complete_following_row'
        return result
    except Exception as exc:errors.append({'phase':'bounded_acquisition','type':type(exc).__name__,'message':str(exc)});result['reason']='bounded_acquisition_abstained';return result
    finally:
        wall=(time.perf_counter()-start)*1000;result['budget']={'limit_ms':budget_ms,'max_calls':max_calls,'calls':len(calls),'returned_wall_ms':wall,'drained_wall_ms':wall,'synchronous_drained':True,'exhausted':wall>budget_ms or any(e['type'] in ('TimeoutError','TimeoutExpired') for e in errors)}
