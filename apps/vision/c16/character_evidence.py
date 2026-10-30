"""Versioned generic exact-fragment character evidence; word policy unchanged.

Character confidences are not calibrated word probabilities. This design helper
must undergo independent negative validation before adoption. It uses no image,
producer or wine identifier, fuzzy edits, or short-code interpretation.
"""
import re
VERSION = 'character-v2'

def inspect_char_run(chars, aliases, min_confidence=90, min_length=5):
    """Find exact catalog alias fragments in geometrically plausible char runs.

    aliases maps normalized alphabetic grape names to canonical catalog grapes.
    Require all characters >=90, length >=5, one canonical dictionary match,
    and plausible individual glyph boxes. Partial words can only support an
    already-retrieved semantic variant; this helper never selects a catalog row.
    """
    parsed=[]
    previous_box=None
    for c in chars:
        title=c.get('title','');box=re.search(r'x_bboxes (\d+) (\d+) (\d+) (\d+)',title)
        confidence=re.search(r'x_conf ([\d.]+)',title)
        if not box or not confidence:return []
        x1,y1,x2,y2=map(int,box.groups());text=c.get('char','').lower()
        if len(text)!=1 or not text.isascii() or not text.isalpha():parsed.append(None);continue
        height=y2-y1;width=x2-x1
        if height<=0 or not .06<=width/height<=1.2:return []
        if previous_box is not None:
            px1,py1,px2,py2=previous_box;previous_height=py2-py1
            if x1<px2 or x1<=px1 or not .6<=height/previous_height<=1.6 or x1-px2>max(height,previous_height):
                return []
        previous_box=[x1,y1,x2,y2]
        if float(confidence.group(1))<min_confidence:
            parsed.append(None);continue
        parsed.append(dict(char=text,confidence=float(confidence.group(1)),box=[x1,y1,x2,y2]))
    runs=[];current=[]
    for c in parsed+[None]:
        if c is None:
            if len(current)>=min_length:runs.append(current)
            current=[];continue
        if current:
            prev=current[-1];height=c['box'][3]-c['box'][1];ph=prev['box'][3]-prev['box'][1]
            gap=c['box'][0]-prev['box'][2]
            # Adjacent character rectangles must not overlap horizontally.
            if not .6<=height/ph<=1.6 or gap>max(height,ph) or gap<0 or c['box'][0]<=prev['box'][0]:
                return []
        current.append(c)
    accepted=[]
    for run in runs:
        value=''.join(c['char'] for c in run)
        # The entire maximal reliable run must be an exact alias substring.
        # Never chop a reliable longer word (FRANCE) down to a grape (FRANC).
        grapes={grape for alias,grape in aliases.items() if value in alias}
        if len(grapes)==1:
            accepted.append(dict(fragment=value,grape=next(iter(grapes)),
                                 aliases=sorted(alias for alias,grape in aliases.items() if value in alias),
                                 min_char_confidence=min(c['confidence'] for c in run)))
    # Distinct semantic grape matches invalidate the entire piece of evidence.
    return accepted if len({r['grape'] for r in accepted})<=1 else []
