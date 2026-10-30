"""Pure plans for additive title observation; no image/OCR/model execution.

One connected cursive stroke is a possible row, never automatically a title.
Whole-grape confidence, role rejection, complete physical-ink observations and
all compatible reference verification remain caller obligations.
"""
import math,time

VERSION = 'context-title-row-normalization-draft-v2-covered-ink-closure'
TARGET_GLYPH_HEIGHT = 48  # Predeclared acquisition hypothesis, not confidence.
MAX_LONG_EDGE = 2000


def observation_context(selected_box, context_box, image_size):
    """Reuse an already measured visual context box; never invent detector extent."""
    x1, y1, x2, y2 = map(float, selected_box)
    a, b, c, d = map(float, context_box)
    width, height = image_size
    if not (0 <= a <= x1 < x2 <= c <= width and 0 <= b <= y1 < y2 <= d <= height):
        raise ValueError('Context must contain selected detector and stay in decoded image')
    return {'selected_detector_box': [x1,y1,x2,y2], 'observation_box': [a,b,c,d],
            'context_is_detector_extent': False,
            'mapping': {'source_offset': [a,b], 'source_scale': [1.,1.]},
            'other_bottle_ambiguity_check_required': True,
            'ranking_views_unchanged': True}


def normalization_plan(source_box, glyph_height, angle_degrees=0, rotated_size=None):
    """Plan size from observed glyph height, independently of recognized literal.

    Supply the actual post-rotation dimensions if deskew is used. PIL's rounded
    rotation extent must not be approximated as an exact coordinate transform.
    Cap is a runtime acquisition bound, not a reason to relax proof thresholds.
    """
    x1,y1,x2,y2 = map(float, source_box)
    if not all(math.isfinite(x) for x in (x1,y1,x2,y2,glyph_height,angle_degrees)):
        raise ValueError('Nonfinite geometry')
    if x2<=x1 or y2<=y1 or glyph_height<=0:
        raise ValueError('Degenerate geometry')
    if rotated_size is None:
        if angle_degrees:
            raise ValueError('Actual post-rotation dimensions required')
        rotated_size = (x2-x1,y2-y1)
    rw,rh = map(float, rotated_size)
    if rw<=0 or rh<=0:
        raise ValueError('Degenerate rotated image')
    scale=min(max(1.,TARGET_GLYPH_HEIGHT/glyph_height),MAX_LONG_EDGE/max(rw,rh))
    nw,nh=max(1,round(rw*scale)),max(1,round(rh*scale))
    return {'version':VERSION,'source_box':[x1,y1,x2,y2],
            'angle_degrees':float(angle_degrees),'rotated_size':[rw,rh],
            'normalized_size':[nw,nh],'actual_scale_x':nw/rw,'actual_scale_y':nh/rh,
            'target_glyph_height':TARGET_GLYPH_HEIGHT,
            'observed_source_glyph_height':float(glyph_height),
            'size_cap_applied':scale<max(1.,TARGET_GLYPH_HEIGHT/glyph_height),
            'target_met':glyph_height*min(nw/rw,nh/rh)>=TARGET_GLYPH_HEIGHT,
            'confidence_unchanged':True,'physical_source_correlation':'same_original_row'}


def inverse_point(point, plan):
    """Map normalized deskew coordinates to decoded source; no EXIF guesswork."""
    x,y=map(float,point);rw,rh=plan['rotated_size'];x/=plan['actual_scale_x'];y/=plan['actual_scale_y']
    x1,y1,x2,y2=plan['source_box'];theta=math.radians(plan['angle_degrees'])
    dx,dy=x-rw/2,y-rh/2;co,si=math.cos(theta),math.sin(theta)
    return [x1+co*dx-si*dy+(x2-x1)/2,y1+si*dx+co*dy+(y2-y1)/2]


def inverse_envelope(box, plan):
    x1,y1,x2,y2=box
    points=[inverse_point(p,plan) for p in ((x1,y1),(x2,y1),(x1,y2),(x2,y2))]
    return {'source_envelope':[min(p[0] for p in points),min(p[1] for p in points),
                               max(p[0] for p in points),max(p[1] for p in points)],
            'source_polygon':points,'envelope_not_exact_rotated_glyph_rectangle':True}


def following_row_nomination(anchor_box, observed_component_boxes, context_size, deadline=None):
    """A full observed connected row can have one component (joined cursive).

    Caller provides ALL unfiltered foreground component bounds from the context,
    not a chosen subset of successful OCR letters. We do not certify unobserved
    ink, semantic role, or query confidence from these bounding rectangles.
    """
    a=list(map(float,anchor_box));h=a[3]-a[1];width,height=context_size
    result={'requested':False,'role_verified':False,'complete_title_proof':False,
            'all_unfiltered_components_required':True,'independent_votes':0}
    if h<=0:return dict(result,reason='degenerate_anchor')
    if len(observed_component_boxes)>1024:
        return dict(result,reason='bounded_component_count_exceeded')
    boxes=[list(map(float,b)) for b in observed_component_boxes]
    if any(len(b)!=4 or not all(math.isfinite(v) for v in b) or b[2]<=b[0] or b[3]<=b[1] for b in boxes):
        return dict(result,reason='invalid_component_geometry')
    eligible=[b for b in boxes if a[3]<b[1]<a[3]+2*h and b[2]>a[0]-h and b[0]<a[2]+h]
    if not eligible:return dict(result,reason='no_observed_following_ink')
    seed=min(eligible,key=lambda b:(b[1],b[0]));group=[seed];remaining=[b for b in eligible if b!=seed]
    for _ in range(len(remaining)+1):
        if deadline is not None and time.perf_counter()>=deadline:
            return dict(result,reason='physical_row_geometry_deadline')
        added=[]
        for b in remaining:
            if deadline is not None and time.perf_counter()>=deadline:
                return dict(result,reason='physical_row_geometry_deadline')
            for z in group:
                bh,zh=b[3]-b[1],z[3]-z[1]
                overlap=max(0,min(b[3],z[3])-max(b[1],z[1]))
                gap=max(0,max(b[0],z[0])-min(b[2],z[2]))
                if overlap>=.2*min(bh,zh) and gap<=.5*max(bh,zh):added.append(b);break
        if not added:break
        group.extend(added);remaining=[b for b in remaining if b not in added]
    b=[min(c[0] for c in group),min(c[1] for c in group),max(c[2] for c in group),max(c[3] for c in group)]
    if b[2]-b[0]<=b[3]-b[1]:return dict(result,reason='not_horizontal_observed_textlike_row')
    if not (0<b[0]<b[2]<width and 0<b[1]<b[3]<height):return dict(result,reason='source_boundary_cut_uncertainty')
    # Connected-component bounding rectangles are not glyph identities. Dots,
    # diacritics and disconnected strokes whose observed bounds intersect the
    # proposed hull must be retained, not interpreted as a failed word proof.
    # Close the observed hull to a fixed point; the initial half-anchor-height
    # vertical border is a fixed acquisition band, never enlarged by chaining.
    if b[3]-b[1]>height/4:
        return dict(result,reason='observed_row_exceeds_existing_text_height_bound')
    initial=list(b);vertical_band=[max(a[3],b[1]-.5*h),min(height,b[3]+.5*h)]
    coverage_added=[];closure_steps=0
    for _ in range(len(boxes)+1):
        if deadline is not None and time.perf_counter()>=deadline:
            return dict(result,reason='physical_ink_coverage_deadline')
        additions=[]
        for c in boxes:
            if deadline is not None and time.perf_counter()>=deadline:
                return dict(result,reason='physical_ink_coverage_deadline')
            if c in group:continue
            intersects=(c[2]>b[0] and c[0]<b[2] and c[3]>b[1] and c[1]<b[3])
            if not intersects:continue
            if c[1]<=a[3] or c[1]<vertical_band[0] or c[3]>vertical_band[1]:
                return dict(result,reason='crossing_anchor_or_separate_row_ink_uncertainty',
                            crossing_component=c,initial_ink_box=initial,
                            fixed_vertical_coverage_band=vertical_band)
            if c[3]-c[1]>height/4:
                return dict(result,reason='nontext_sized_crossing_component',crossing_component=c)
            additions.append(c)
        if not additions:break
        group.extend(additions);coverage_added.extend(additions);closure_steps+=1
        b=[min(c[0] for c in group),min(c[1] for c in group),
           max(c[2] for c in group),max(c[3] for c in group)]
        if not (0<b[0]<b[2]<width and 0<b[1]<b[3]<height):
            return dict(result,reason='source_boundary_cut_after_coverage_closure')
        if b[1]<vertical_band[0] or b[3]>vertical_band[1]:
            return dict(result,reason='row_coverage_expansion_ambiguous')
    else:
        return dict(result,reason='bounded_ink_coverage_closure_incomplete')
    # The hull describes all provided foreground in this physical band, not
    # completeness of unseen letters or semantic title role. Retain provenance.
    return dict(result,requested=True,observed_ink_box=b,component_boxes=group,
                component_count=len(group),initial_ink_box=initial,
                coverage_added_components=coverage_added,coverage_closure_steps=closure_steps,
                fixed_vertical_coverage_band=vertical_band,
                reason='observed_whole_connected_following_row_nomination',
                required_proofs=['unfiltered_foreground_row_boundary_coverage',
                                 'positive_reliable_whole_grape_anchor',
                                 'no_positive_non_title_observation',
                                 'all_compatible_source_bound_reference_rows_and_scores'])
