"""Exact Unicode descriptor evidence; word and glyph confidence stay distinct."""
import math,re,unicodedata
import numpy as np
from gram_ocr import norm
VERSION='unicode-complete-descriptor-geometry-v2-boundary-punctuation'
FORMS={
 'color':{'white':{'beloe','belyy','belyj','belye'},'red':{'krasnoe','krasnyy','krasnyj','krasnye'},'rose':{'rozovoe','rozovyy','rozovyj','rozovye'}},
 'sugar':{'semi_sweet':{'polusladkoe','polusladkiy'},'semi_dry':{'polusuhoe','polusuhoj'},'sweet':{'sladkoe','sladkiy'},'dry':{'suhoe','suhoj','suhoy'},'brut':{'bryut'}}}

def complete_descriptor(text):
    token=norm(text)
    if len(token.split())!=1:return []
    return [(key,value) for key,values in FORMS.items() for value,aliases in values.items() if token in aliases]

def verify_word(word, pixels):
    """No suffix, arbitrary run window, or low-confidence glyph may be trusted.

    hOCR bounding rectangles can overlap for italic strokes. Validate small
    overlap using ordered centers, robust scale, word bounds and actual ink;
    reject gross overlap, collapsed glyphs, merged boxes and empty ink regions.
    This is a new evidence channel, not modification of frozen Latin V2.
    """
    raw_chars=word.get('chars',[]);literal=''.join(c.get('char','') for c in raw_chars)
    start=0;end=len(raw_chars)
    def punctuation(char):
        text=char.get('char','')
        return len(text)==1 and unicodedata.category(text).startswith('P')
    while start<end and punctuation(raw_chars[start]):start+=1
    while end>start and punctuation(raw_chars[end-1]):end-=1
    chars=raw_chars[start:end];core=''.join(c.get('char','') for c in chars)
    boundary=[]
    for n,char in enumerate(raw_chars):
        if start<=n<end:continue
        q=re.search(r'x_conf ([0-9.]+)',char.get('title',''))
        boundary.append({'position':n,'side':'leading' if n<start else 'trailing','char':char.get('char',''),'title':char.get('title',''),'confidence':float(q[1]) if q else None})
    result={'literal':literal,'alphabetic_core':core,'core_positions':[start,end],
            'boundary_punctuation':boundary,'accepted':False,'chars':raw_chars,
            'core_chars':chars,'geometry_version':VERSION}
    def reject(reason):return dict(result,reason=reason)
    # Only Unicode punctuation may bound a whole token. Letters, digits,
    # unknown symbols, internal punctuation and multiple alpha runs survive
    # unchanged into this predicate and are rejected, never silently cleaned.
    if len(chars)<5 or not all(len(c.get('char',''))==1 and c['char'].isalpha() for c in chars):return reject('not_complete_alphabetic_token_at_least5')
    matches=complete_descriptor(core)
    if len(matches)!=1:return reject('not_one_exact_global_descriptor')
    token=norm(core)
    # A missing prefix can turn semi-dry/sweet into a complete dry/sweet word.
    # Character-only evidence conservatively abstains for such suffix aliases.
    if matches[0][0]=='sugar' and any(alias!=token and alias.endswith(token) for values in FORMS['sugar'].values() for alias in values):return reject('potential_truncated_descriptor_suffix')
    rect=re.search(r'bbox (\d+) (\d+) (\d+) (\d+)',word.get('title',''))
    if not rect:return reject('missing_word_box')
    bounds=list(map(int,rect.groups()));boxes=[];conf=[]
    for char in chars:
        b=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',char.get('title',''));q=re.search(r'x_conf ([0-9.]+)',char.get('title',''))
        if not b or not q:return reject('missing_character_geometry_or_confidence')
        box=list(map(int,b.groups()));c=float(q[1])
        if not math.isfinite(c) or c<90:return reject('character_below90')
        boxes.append(box);conf.append(c)
    widths=np.asarray([b[2]-b[0] for b in boxes]);heights=np.asarray([b[3]-b[1] for b in boxes]);mw=float(np.median(widths));mh=float(np.median(heights))
    if mw<=0 or mh<=0:return reject('degenerate_glyph')
    ink=np.asarray(pixels.convert('L'));observed=[]
    for n,b in enumerate(boxes):
        x1,y1,x2,y2=b;w=x2-x1;h=y2-y1
        if not (0<=x1<x2<=ink.shape[1] and 0<=y1<y2<=ink.shape[0]):return reject('glyph_outside_image')
        if not (bounds[0]<=x1<x2<=bounds[2] and bounds[1]<=y1<y2<=bounds[3]):return reject('glyph_outside_word')
        if not (.06<=w/h<=2.0 and .35<=h/mh<=2.5 and w/mw<=2.5):return reject('collapsed_or_merged_glyph')
        occupancy=float(np.mean(ink[y1:y2,x1:x2]<128));observed.append(occupancy)
        if not .03<=occupancy<=.85:return reject('missing_or_solid_ink')
        if n:
            p=boxes[n-1];pw=p[2]-p[0]
            if (x1+x2)/2<=(p[0]+p[2])/2:return reject('nonmonotonic_centers')
            if max(0,p[2]-x1)>.25*min(pw,w):return reject('excessive_overlap')
            if x1-p[2]>mh or abs((y1+y2-p[1]-p[3])/2)>mh:return reject('disconnected_glyph_sequence')
    key,value=matches[0]
    return dict(result,accepted=True,key=key,value=value,reason='exact_complete_token_high_character_confidence_geometry_verified',minimum_character_confidence=min(conf),boxes=boxes,ink_occupancy=observed)
