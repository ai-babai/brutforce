"""Frozen architectural candidate: original retrieval + constrained evidence.

Observe actual original computations. No model proxy, score recomputation,
wine-specific rule, query identity, new model, or global patch.
"""
import json,math,threading,time,io,hashlib
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from pathlib import Path
import numpy as np
from workflow_trace import instrument
from gram_ocr import CatalogAttributes,recognize
from constraint_policy import CatalogFamilies as VisualFamilies, needs_text as visual_needs_text
from character_acquisition import acquire
from candidate_policy import CatalogFamilies,rank,visual_decision,needs_text,text_decision,reliable_query,coherent_support,query_attributes,KEYS
from expanded_policy import ExpansionFamilies, needs_acquisition, expansion_decision
from semantic_acquisition import acquire as acquire_semantic
from title_catalog import TitleCatalog
from title_geometry import extract as acquire_title
from context_title_acquisition import extract as acquire_context_title
from context_title_gallery import ContextTitleGallery
from context_title_verification import gate as context_gate, decide as context_decision
from title_context_geometry import observation_context
from title_gallery import TitleGallery
from title_verification import decide as title_decision
from query_text_canvas import build as build_text_canvas
from local_grape_acquisition import acquire as acquire_local_grape
from field_acquisition import acquire as acquire_resource_fields
from acquisition_gate import plan as resource_field_plan
from field_contract import registry as field_registry, verify_selection as resource_field_selection
from positive_signature import decide as positive_signature_decision
from upper_gallery import UpperGallery
from artwork_gallery import ArtworkGallery
from artwork_pairwise import decide as artwork_pairwise_decision
from upper_policy import nominate as upper_nominate, select as upper_select

class Capture:
    def __init__(self, owner):self.data={};self.capture_errors=[];self.owner=owner;self.jobs=None
    def capture(self,name,v):
        if name=='decode':self.data['image']=v['image']
        elif name=='crop_gate':self.data.update(crop_needed=bool(v['crop_needed']),full_scores=v['final_scores'])
        elif name=='detector':
            self.data.update(box=list(v['central']),detector_boxes=v['boxes'])
            # Same family ambiguity gate, evaluated from the available full view.
            # Prefetch only in the existing <=.05 crop branch. Nothing is ranked
            # by prefetched text until the original post-fusion gate accepts it.
            order=rank(self.data['full_scores'])
            # The eventual label-gallery Top5 can contain family variants absent
            # from the full-gallery Top5. Anticipate family ambiguity from the
            # catalogue, without changing the final visual/text shortlist.
            if self.owner.prefetch_variants[int(order[0])]:
                self.jobs=self.owner.start_ocr(self.data['image'],self.data['box'])
        elif name=='fusion':
            self.data.update(scores=(v['scores']['fullframe'],v['scores']['central_pad25'],v['legacy_scores']),base_scores=v['final_scores'],all_view_scores=v['scores'])

class ConstraintBoost:
    def __init__(self,engine,policy,catalog_path,ocr_assets,original_runtime):
        self.engine,self.policy,self.ocr_assets=engine,policy,ocr_assets
        self.core=instrument(original_runtime)
        attrs=CatalogAttributes(ocr_assets['metadata_path'],engine.slugs)
        references=json.loads(catalog_path.read_text())['references']
        self.families=CatalogFamilies(references,attrs)
        self.visual_families=VisualFamilies(references,attrs)
        self.expansion_families=ExpansionFamilies(references,attrs)
        self.title_catalog=TitleCatalog(references,self.families)
        self.title_gallery=TitleGallery(Path(__file__).resolve().parent,catalog_path,ocr_assets["metadata_path"],references,engine)
        self.context_title_gallery=ContextTitleGallery(Path(__file__).resolve().parent,catalog_path,ocr_assets["metadata_path"],references,engine,self.title_gallery)
        self.context_references=references
        self.resource_lexicon,self.resource_contexts=field_registry(attrs.vocab,references,self.expansion_families)
        self.upper_gallery=UpperGallery(Path(__file__).resolve().parent,references,self.title_gallery,engine,
            expected_manifest_sha256='ce1fc24b41cd431f11398dce0b421f4675df6d9e4074dfb98bdf1c0c55a23d1d',expected_features_sha256='fa27702dfd3ac06a88d69e47bf9f762f4a730f4a14be81e089b24e0580c8618c')
        self.artwork_gallery=ArtworkGallery(Path(__file__).resolve().parent,self.upper_gallery,
            expected_manifest_sha256='13d2c4150f4ff63bed2557137769f90fd92e920c2e70e413b5fbeb2172750794',expected_features_sha256='03007acd3e25800aa0567319cec8199e130cda5f419426c9d3c6373a8d9949de')
        by_producer={}
        for i,producer in enumerate(self.families.producer):by_producer.setdefault(producer,[]).append(i)
        self.prefetch_variants=[any((self.families.same(i,j) or self.visual_families.same(i,j)) and
                                   any(attrs.rows[i][k]!=attrs.rows[j][k] for k in ('grape','color','sugar'))
                                   for j in by_producer[producer])
                                for i,producer in enumerate(self.families.producer)]
        self.lock=threading.Lock()
        self.ocr_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='constraint-ocr')

    def predict(self,content,catalog_version='original2103',index_version='Batch32'):
        with self.lock:return self._predict(content,catalog_version,index_version)

    def start_ocr(self,image,box):
        x1,y1,x2,y2=box;bw,bh=x2-x1,y2-y1
        body_box=[max(0,math.floor(x1+.06*bw)),max(0,math.floor(y1+.30*bh)),
                  min(image.width,math.ceil(x1+.94*bw)),min(image.height,y2)]
        body=image.crop(body_box);lower=body.crop((0,math.floor(.60*body.height),body.width,body.height))
        jobs=[self.ocr_pool.submit(recognize,roi,self.ocr_assets,preprocess=True,
                                  timeout=2,psm=11,return_words=True) for roi in (body,lower)]
        return body_box,jobs

    def _predict(self,content,catalog_version,index_version):
        start=time.perf_counter();capture=Capture(self)
        result=self.core.predict(self.engine,content,self.policy,catalog_version,index_version,_workflow_observer=capture)
        result['boost']['policy']='boost_independent_recovery_v16_c16'
        if capture.capture_errors:raise RuntimeError('Original score observation failed')
        flags={'baseline_slug':result.get('slug'),'consensus_override':False,'text_override':False,
               'ocr_used':False,'ocr_errors':[],'blocked_color_conflict':False,
               'ocr_prefetched':capture.jobs is not None,'unused_prefetch_cancelled':0,
               'qualification':'DEVELOPMENT_UNQUALIFIED'}
        if not capture.data['crop_needed']:
            result['evidence']=flags
            result['timings_ms']['total_ms']=round(1000*(time.perf_counter()-start))
            return result
        scores=capture.data['scores'];base_scores=capture.data['base_scores'];base_order=rank(base_scores)
        flags['current_gallery_votes']=[int(rank(capture.data['all_view_scores'][k])[0]) for k in ('fullframe','central_pad25','central_pad10')]
        flags['original_base_top20']=[int(i) for i in base_order[:20]]
        assert str(self.engine.slugs[int(base_order[0])])==result['slug'],'Original score observation drift'
        # Physical views vote in the same current gallery; historical vectors stay in the original cascade only.
        proposal_scores=tuple(capture.data['all_view_scores'][k] for k in ('fullframe','central_pad25','central_pad10'))
        boxes=[result['boost']['boxes'][k] for k in ('fullframe','central_pad25','central_pad10')]
        legacy_order,legacy_decision=visual_decision(base_order,scores,self.visual_families,boxes)
        coherent_order,coherent_decision=visual_decision(base_order,proposal_scores,self.visual_families,boxes)
        order=legacy_order
        flags.update(legacy_decision)
        flags.update(visual_vote_gallery='V6 proposal retained; current-gallery nomination requires separate varietal support',
                     legacy_visual_decision=legacy_decision,coherent_visual_nomination=coherent_decision)
        semantic_gate=needs_text(base_order,base_scores,coherent_decision['visual_votes'],self.families)
        visual_gate=visual_needs_text(base_order,base_scores,legacy_decision['visual_votes'],self.visual_families)
        flags.update(semantic_text_gate=bool(semantic_gate),visual_text_gate=bool(visual_gate),visual_family_scope='frozenV6',semantic_family_scope='catalog_variant_v7')
        title_contenders=self.title_catalog.contenders(int(base_order[0]),base_order)
        title_gate=bool(self.title_catalog.ambiguity(int(base_order[0]),base_order) and not title_contenders['unknown'] and self.title_gallery.ready(title_contenders['known']))
        flags['title_verification']={'gate':title_gate,'nomination':title_contenders,'gallery':self.title_gallery.assets,'title_override':False,'reason':'no_complete_known_title_gallery_ambiguity'}
        words=[];expansion_query={k:set() for k in KEYS}
        if semantic_gate or visual_gate:
            step=time.perf_counter()
            body_box,jobs=capture.jobs or self.start_ocr(capture.data['image'],capture.data['box'])
            words=[]
            for job in jobs:
                try:words.append(job.result())
                except Exception as exc:words.append([]);flags['ocr_errors'].append(type(exc).__name__)
            flags.update(ocr_used=True,ocr_box=body_box,ocr_words=words)
            if coherent_decision['consensus_override']:
                order,support_flags=coherent_support(base_order,legacy_order,coherent_order,words,self.families)
            else:
                order=legacy_order
                support_flags={'coherent_support_override':False,'reason':'no_eligible_distinct_current_gallery_nomination'}
            flags['coherent_verification']=support_flags
            flags['coherent_support_override']=bool(support_flags['coherent_support_override'])
            query=reliable_query(words,self.families.attributes)
            group=[int(i) for i in base_order[:5] if self.families.same(int(base_order[0]),int(i))]
            variants=set().union(*(self.families.attributes.rows[i]['grape'] for i in group))
            character_query={}
            word_order,word_flags=text_decision(base_order,order,words,self.families)
            # Bounded fallback for unresolved varietal ambiguity in the same visual family.
            if not word_flags['text_override'] and len(group)>=2 and len(variants)>1 and not query['grape'] and all(len(v)<=1 for v in query.values()):
                char_start=time.perf_counter()
                character=acquire(capture.data['image'],capture.data['box'],self.ocr_assets,self.families.attributes.vocab)
                flags['character_ocr']=character
                accepted=set(character.get('accepted_grapes',[]))
                character_query={'grape':accepted if accepted<=variants else set()}
                flags['character_family_gate']=bool(accepted and accepted<=variants)
                result['timings_ms']['character_ocr_ms']=round(1000*(time.perf_counter()-char_start))
            if any(character_query.values()):
                order,text_flags=text_decision(base_order,order,words,self.families,character_query=character_query)
            else:order,text_flags=word_order,word_flags
            flags.update(text_flags)
            # Keep deployed C05 proposal and OCR ranking as the default. A
            # separate verifier may extend existing retrieval only after new
            # complete semantic evidence contradicts this final C05 head.
            expansion_query=reliable_query(words,self.families.attributes)
            for key,values in character_query.items():
                expansion_query[key] |= set(values)
            acquisition_gate=needs_acquisition(base_order,order,words,self.expansion_families)
            flags['semantic_acquisition_gate']=bool(acquisition_gate)
            if acquisition_gate:
                semantic_start=time.perf_counter()
                semantic=acquire_semantic(capture.data['image'],capture.data['box'],self.ocr_assets,pass_words=words)
                flags['semantic_acquisition']=semantic
                for key,values in semantic.get('accepted_fields',{}).items():
                    if key not in expansion_query:raise ValueError('Unknown semantic evidence field')
                    expansion_query[key] |= set(values)
                result['timings_ms']['semantic_acquisition_ms']=round(1000*(time.perf_counter()-semantic_start))
            # Preserve blend ambiguity rather than trusting a filtered subset.
            if text_flags.get('raw_multi_grape_uncertainty'):
                expansion_query['grape']=set()
            order,expansion_flags=expansion_decision(base_order,order,expansion_query,self.expansion_families,
                 evidence=flags.get('semantic_acquisition',{}).get('evidence',[]))
            flags['semantic_expansion']=expansion_flags
            flags['semantic_expansion_override']=bool(expansion_flags['expansion_override'])
            result['timings_ms']['ocr_ms']=round(1000*(time.perf_counter()-step))
        elif capture.jobs and not title_gate:
            flags['unused_prefetch_cancelled']=sum(job.cancel() for job in capture.jobs[1])
        if title_gate:
            title_start=time.perf_counter()
            # Existing prefetch supplies language and independent reliable
            # contradictions even when C08's semantic/visual gates abstain.
            if not flags['ocr_used']:
                body_box,jobs=capture.jobs or self.start_ocr(capture.data['image'],capture.data['box'])
                for job in jobs:
                    try:words.append(job.result())
                    except Exception as exc:words.append([]);flags['ocr_errors'].append(type(exc).__name__)
                flags.update(ocr_used=True,ocr_box=body_box,ocr_words=words,title_only_word_acquisition=True)
                expansion_query=reliable_query(words,self.families.attributes)
            order,title_flags=self.verify_title(base_order,order,expansion_query,words,capture.data['image'],capture.data['box'])
            flags['title_verification']=dict(title_flags,gate=True,gallery=self.title_gallery.assets)
            flags['title_override']=bool(title_flags['title_override'])
            result['timings_ms']['title_verification_ms']=round(1000*(time.perf_counter()-title_start))
        # Deployed C09 acquisition and decisions remain the default. Raw OCR
        # nominates one unresolved field only; it never becomes trusted proof.
        raw_text=' '.join(str(w['text']) for passage in words for w in passage)
        raw_query=query_attributes(self.families.attributes,raw_text)
        original_group=[int(i) for i in base_order[:5] if self.families.same(int(base_order[0]),int(i))]
        original_variants=set().union(*(self.families.attributes.rows[i]['grape'] for i in original_group))
        local_gate=bool(words and len(raw_query['grape'])==1 and raw_query['grape']<=original_variants
                        and len(original_group)>=2 and len(original_variants)>1 and not expansion_query['grape']
                        and not any(flags.get(k,False) for k in ('text_override','coherent_support_override','semantic_expansion_override','title_override'))
                        and all(len(v)<=1 for v in expansion_query.values()))
        flags['local_grape_verification']={'gate':local_gate,'reason':'existing_C09_not_unresolved_unique_raw_grape'}
        if local_gate:
            local_start=time.perf_counter()
            try:
                with Image.open(io.BytesIO(content)) as stored:
                    source_size=stored.size;orientation=stored.getexif().get(274)
                canvas=build_text_canvas(capture.data['image'],capture.data['box'],source_size=source_size,exif_orientation=orientation)
                acquired=acquire_local_grape(canvas.image,canvas.central_box,self.ocr_assets,self.families.attributes.vocab)
                flags['local_grape_verification']=dict(acquired,gate=True,text_preprocessing=canvas.provenance,
                    evidence_coordinate_space='text_canvas_pixel_edges',decoded_coordinate_mapping=canvas.provenance['text_to_decoded_matrix'])
                accepted=set(acquired.get('accepted_grapes',[]))
                if accepted and accepted<=original_variants and accepted==raw_query['grape']:
                    order,local_decision=text_decision(base_order,order,words,self.families,character_query={'grape':accepted})
                    flags['local_grape_verification']['selection']=local_decision
                    flags['local_grape_override']=bool(local_decision['text_override'])
                    expansion_query['grape']|=accepted
                else:flags['local_grape_override']=False
                result['timings_ms']['text_preprocessing_ms']=canvas.provenance['preprocessing_wall_ms']
            except Exception as exc:
                # New optional acquisition cannot break a valid deployed request.
                flags['local_grape_verification'].update(error_type=type(exc).__name__,reason='optional_local_verification_abstained')
                flags['local_grape_override']=False
            result['timings_ms']['local_grape_verification_ms']=round(1000*(time.perf_counter()-local_start))
        # C13 is the default. Acquire independent complete fields only after a
        # measured PRE-OCR resource abort; never relax global noise/word gates.
        order=self.verify_resource_and_upper(base_order,order,expansion_query,raw_query,
             capture.data,content,flags,result)
        order=self.verify_context_title(base_order,order,expansion_query,raw_query,capture.data,result,flags)
        ranked=[str(self.engine.slugs[int(i)]) for i in order if np.isfinite(base_scores[int(i)])][:20]
        result['ranked_slugs'],result['slug']=ranked,ranked[0]
        result['evidence']=flags
        result['boost']['policy']='boost_independent_recovery_v16_c16'
        result['timings_ms']['total_ms']=round(1000*(time.perf_counter()-start))
        return result

    def verify_context_title(self,base_order,order,query,raw_query,observed,result,flags):
        started=time.perf_counter();details={'context_title_override':False,'model_calls':0,'errors':[],'synchronous_drained':True,'gallery':self.context_title_gallery.assets}
        def no(reason):
            details['reason']=reason
            return order
        try:
            raw_blend=len(raw_query.get('grape',()))>1 or bool(flags.get('raw_multi_grape_uncertainty'))
            nomination=context_gate(base_order,order,query,self.families,self.context_references,flags,lambda i:self.context_title_gallery.ready([i]),raw_blend)
            details['nomination']=nomination
            if not nomination.get('requested'):return no(nomination['reason'])
            if not nomination.get('reference_set_ready'):return no('all_required_known_distinct_reference_title_proofs_unavailable')
            image=observed['image'];selected=observed['box'];pad=result['boost']['boxes']['central_pad25']
            context=observation_context(selected,pad,image.size);context_box=[int(pad[0]),math.floor(selected[1]+.60*(selected[3]-selected[1])),int(pad[2]),int(pad[3])]
            if not (context_box[0]<context_box[2] and context_box[1]<context_box[3]):return no('no_complete_lower_observation_corridor')
            details['observation_context']=dict(context,acquisition_box=context_box,role='lower_corridor_of_existing_measured_visual_context',new_detector_extent_inferred=False)
            acquired=acquire_context_title(image.crop(context_box),self.ocr_assets,self.families.attributes.vocab)
            acquired['coordinate_space']='observation_corridor_pixel_edges'
            acquired['context_to_decoded_matrix']=[[1,0,context_box[0]],[0,1,context_box[1]],[0,0,1]]
            acquired['original_image_char_rects_frame']='local_acquisition_image_not_full_decoded_image'
            mapped_chars=[]
            for call in acquired.get('calls',[]):
                for item in call.get('evidence',[]):
                    for ch in item.get('original_image_char_rects',[]):
                        z=dict(ch)
                        if ch.get('source_envelope'):
                            b=ch['source_envelope'];z['decoded_source_envelope']=[b[0]+context_box[0],b[1]+context_box[1],b[2]+context_box[0],b[3]+context_box[1]]
                        if ch.get('source_polygon'):z['decoded_source_polygon']=[[x+context_box[0],y+context_box[1]] for x,y in ch['source_polygon']]
                        mapped_chars.append(z)
            acquired['decoded_character_observations']=mapped_chars
            details['query_acquisition']=acquired
            if not acquired.get('accepted'):return no('no_complete_positive_context_title_observation')
            source_boxes=[]
            for b in [acquired['anchor']['ink_box'],acquired['following_row']['ink_box'],acquired['box']]:
                b=[b[0]+context_box[0],b[1]+context_box[1],b[2]+context_box[0],b[3]+context_box[1]];source_boxes.append(b)
                # Keep selected bottle's measured horizontal identity. Only
                # the observed visual-context vertical corridor is extended.
                if not (selected[0]<=b[0]<b[2]<=selected[2] and context_box[1]<=b[1]<b[3]<=context_box[3]):return no('row_outside_selected_axis_or_observed_context')
            details['decoded_source_boxes']=source_boxes
            # Alternative detector fragments on the same axis are correlated
            # observations. A distinct bottle axis crossing this text is unknown.
            ink=source_boxes[1];sx=(selected[0]+selected[2])/2;sw=selected[2]-selected[0];ambiguous=[]
            for other in observed.get('detector_boxes',[]):
                b=other.get('box') if isinstance(other,dict) else other
                if not isinstance(b,(tuple,list)) or len(b)!=4:continue
                cx=(b[0]+b[2])/2
                horizontal_overlap=max(0,min(ink[2],b[2])-max(ink[0],b[0]));vertical_overlap=max(0,min(ink[3],b[3])-max(ink[1],b[1]))
                axis_scale=min(sw,b[2]-b[0]);same_axis=axis_scale>0 and abs(cx-sx)<=.10*axis_scale
                if horizontal_overlap>0 and vertical_overlap>0 and not same_axis:ambiguous.append(b)
            details['axis_alignment_contract']={'maximum_center_offset_fraction_of_smaller_box_width':.10,'all_detector_scores_considered':True,'same_axis_fragments_correlated_not_independent':True}
            details['other_bottle_axis_conflicts']=ambiguous
            if ambiguous:return no('different_bottle_axis_overlaps_observed_title')
            box=source_boxes[2];crop=image.crop(box).convert('RGB')
            if acquired.get('angle_degrees'):crop=crop.rotate(acquired['angle_degrees'],Image.Resampling.BICUBIC,expand=True,fillcolor=(255,255,255))
            contenders=nomination['required_contenders'];feature_start=time.perf_counter();details['model_calls']=1
            feature=self.engine.model.so_embedder.features([crop])[0];details['feature_wall_ms']=1000*(time.perf_counter()-feature_start)
            scores=self.context_title_gallery.score(feature,contenders)
            chosen,decision=context_decision(base_order,order,query,self.families,self.context_references,acquired,scores,self.context_title_gallery.proofs,flags,raw_blend,catalog_sha256=self.context_title_gallery.manifest['catalog_sha256'])
            details.update(decision,reference_proofs={str(i):self.context_title_gallery.proofs[i] for i in contenders})
            flags['context_title_override']=bool(decision['context_title_override'])
            return chosen
        except Exception as exc:
            details['errors'].append({'type':type(exc).__name__,'message':str(exc)})
            return no('optional_context_title_error_preserve_current_C14')
        finally:
            details['returned_wall_ms']=1000*(time.perf_counter()-started);details['drained_wall_ms']=details['returned_wall_ms'];flags['context_title_verification']=details
            result['timings_ms']['context_title_verification_ms']=round(details['returned_wall_ms'])

    def verify_resource_and_upper(self,base_order,order,query,raw_query,observed,content,flags,result):
        started=time.perf_counter()
        strong_keys=('semantic_expansion_override','title_override','coherent_support_override','local_grape_override','resource_semantic_override','resource_signature_override')
        prior={k:bool(flags.get(k,False)) for k in strong_keys}
        character=flags.get('character_ocr',{})
        gate=resource_field_plan(base_order,order,query,raw_query,self.expansion_families,character,
              prior_overrides=dict(prior,text_override=bool(flags.get('text_override'))))
        details={'plan':gate,'override':False,'errors':[],'returned_wall_ms':None,'drained_wall_ms':None}
        flags['resource_field_verification']=details
        incoming_order=order
        def incomplete(reason):
            # Failed or incomplete acquisition is unknown, never a completed
            # no-trusted-fields observation opening a visual fallback.
            details.update(acquisition_completion_state='INCOMPLETE',reason=reason)
            details['returned_wall_ms']=1000*(time.perf_counter()-started)
            details['drained_wall_ms']=details['returned_wall_ms']
            flags['upper_view_verification']={'nomination':{'requested':False,'reason':reason},
                'override':False,'errors':[],'blocked_by_incomplete_text_observation':True,
                'same_physical_view_correlated_evidence':True}
            result['timings_ms']['resource_upper_verification_ms']=round(details['returned_wall_ms'])
            return incoming_order
        prior_word_errors=list(flags.get('ocr_errors',()))
        timeout_recovery=bool(prior_word_errors and all(e=='TimeoutExpired' for e in prior_word_errors)
            and gate.get('requested'))
        details['independent_timeout_recovery']={
            'requested':timeout_recovery,'prior_errors_retained':prior_word_errors,
            'failed_prior_observation_is_unknown':bool(prior_word_errors),
            'negative_absence_inferred':False,
            'allowed_channel':'complete_actual_word90_positive_product_color_only'}
        if prior_word_errors and not timeout_recovery:
            return incomplete('prior_word_acquisition_incomplete_preserve_C13')
        verified_query={k:set(query.get(k,())) for k in KEYS}
        if gate.get('requested'):
            try:
                with Image.open(io.BytesIO(content)) as stored:
                    source_size=stored.size;orientation=stored.getexif().get(274)
                canvas=build_text_canvas(observed['image'],observed['box'],source_size=source_size,exif_orientation=orientation)
                acquired=acquire_resource_fields(canvas.image,canvas.central_box,self.ocr_assets,self.resource_lexicon)
                details.update(acquisition=acquired,text_preprocessing=canvas.provenance,
                    evidence_coordinate_space='text_canvas_pixel_edges',decoded_coordinate_mapping=canvas.provenance['text_to_decoded_matrix'])
                budget=acquired.get('budget',{})
                attempted=budget.get('calls_attempted');completed=budget.get('calls_completed')
                if (acquired.get('errors') or budget.get('exhausted') is not False
                    or type(attempted) is not int or attempted<1 or type(completed) is not int
                    or completed!=attempted or not isinstance(acquired.get('accepted_fields'),dict)
                    or acquired.get('reason')=='conflicting_fields_abstain'):
                    return incomplete('resource_acquisition_incomplete_or_conflicting_preserve_C13')
                fields=acquired['accepted_fields']
                details['acquisition_completion_state']=('COMPLETED_OBSERVED_FIELDS_UNVERIFIED'
                    if any(fields.values()) else 'COMPLETED_NO_TRUSTED_FIELDS')
                details['semantic_absence_inferred']=False
                complete={k:set(query.get(k,()))|set(fields.get(k,())) for k in KEYS}
                complete['product']=set(fields.get('product',()))
                if len(raw_query.get('grape',()))<=1 and not flags.get('raw_multi_grape_uncertainty'):
                    # Observed field strings do not resolve catalog identity.
                    # A standalone varietal can be a family root of a compound
                    # catalog value; it cannot eliminate an unverified subtype.
                    details['semantic_selection']={'override':False,'reason':'resource_observation_requires_complete_positive_product_color_identity'}
                    stats=character.get('proposal_budget',{})
                    if fields.get('grape'):
                        selected=order
                        signature={'override':False,'reason':'new_varietal_root_or_compound_identity_unverified_observation_retained'}
                    else:
                        selected,signature=positive_signature_decision(base_order,order,acquired,query,raw_query,
                            self.expansion_families,self.resource_contexts,
                            {'reason':stats.get('abort_reason'),'OCR_calls':character.get('calls_attempted',0)},
                            {k:bool(flags.get(k,False)) for k in strong_keys})
                    details['positive_signature']=signature
                    if signature.get('override'):
                        order=selected;flags['resource_signature_override']=True
                    details['resource_fields_not_used_as_upper_constraints']=True
                details['override']=bool(flags.get('resource_semantic_override') or flags.get('resource_signature_override'))
            except Exception as error:
                details['errors'].append({'type':type(error).__name__,'message':str(error)[:300]})
                return incomplete('optional_resource_acquisition_error_preserve_C13')
        if timeout_recovery:
            # A failed earlier observation cannot open visual/absence channels.
            # Only this separate, fully completed positive identity proof may
            # correct the proposal; raw errors and contradictions remain visible.
            recovered=bool(details.get('positive_signature',{}).get('override'))
            details['independent_timeout_recovery']['positive_identity_verified']=recovered
            flags['upper_view_verification']={'nomination':{'requested':False,
                'reason':'prior_word_timeout_no_visual_absence_fallback'},
                'override':False,'errors':[],'blocked_by_incomplete_text_observation':True,
                'same_physical_view_correlated_evidence':True}
            details['returned_wall_ms']=1000*(time.perf_counter()-started)
            details['drained_wall_ms']=details['returned_wall_ms']
            result['timings_ms']['resource_upper_verification_ms']=round(details['returned_wall_ms'])
            return order if recovered else incoming_order
        details['returned_wall_ms']=1000*(time.perf_counter()-started);details['drained_wall_ms']=details['returned_wall_ms']
        prior={k:bool(flags.get(k,False)) for k in strong_keys}
        # Independent extra visual view is limited to original Top20. Every
        # compatible/unknown source must participate, never missing=conflict.
        nomination=upper_nominate(base_order,order,verified_query,raw_query,self.expansion_families,character,prior)
        acquired_fields=details.get('acquisition',{}).get('accepted_fields',{})
        if any(acquired_fields.values()):
            nomination=dict(nomination,requested=False,reason='genuine_resource_fields_preserved_requires_positive_catalog_identity_verification',observed_fields=acquired_fields)
        upper={'nomination':nomination,'override':False,'errors':[],'same_physical_view_correlated_evidence':True}
        flags['upper_view_verification']=upper
        if nomination.get('requested') and not any(prior.values()):
            try:
                acquired=self.upper_gallery.query(observed['image'],hashlib.sha256(content).hexdigest(),
                    observed['box'],observed['detector_boxes'],nomination['required_contenders'])
                upper['acquisition']=acquired
                if acquired.get('accepted'):
                    selected,decision=upper_select(order,nomination,acquired['query_geometry'],
                        acquired['reference_proofs'],acquired['scores'],acquired['expected_identity'])
                    upper['selection']=decision
                    if decision.get('override'):
                        order=selected;upper['override']=True;flags['upper_view_override']=True
                    elif not any(verified_query.values()):
                        # This is proposal-versus-current-head verification,
                        # not a global hue winner or independent physical vote.
                        # All source-bound competitors, including unknowns,
                        # remain scored and retained in the actual trace.
                        artwork_start=time.perf_counter()
                        needed=nomination['required_contenders']
                        if self.artwork_gallery.ready(needed):
                            query_artwork=self.artwork_gallery.query(observed['image'],acquired['query_geometry'])
                            refs=self.artwork_gallery.references(needed)
                            selected,appearance=artwork_pairwise_decision(base_order,order,nomination,acquired,
                                verified_query,raw_query,character,dict(prior,text_override=bool(flags.get('text_override'))),query_artwork,refs)
                            upper['pairwise_artwork']=dict(appearance,query_descriptor=query_artwork,
                                reference_descriptors=refs,gallery=self.artwork_gallery.assets,
                                wall_ms=1000*(time.perf_counter()-artwork_start))
                            if appearance.get('override'):
                                order=selected;upper['override']=True;flags['upper_artwork_override']=True
                        else:upper['pairwise_artwork']={'override':False,'reason':'all_unknown_reference_artwork_must_be_ready'}
            except Exception as error:
                upper['errors'].append({'type':type(error).__name__,'message':str(error)[:300]})
                upper['reason']='optional_upper_verification_error_preserve_C13'
        result['timings_ms']['resource_upper_verification_ms']=round(1000*(time.perf_counter()-started))
        return order

    def verify_title(self,base_order,order,query,words,image,central_box):
        started=time.perf_counter();details={'title_override':False,'returned_wall_ms':None,'drained_wall_ms':None,'synchronous_drained':True,'model_calls':0,'errors':[]}
        def abstain(reason):
            details['reason']=reason
            return order,details
        try:
            raw_text=' '.join(str(text) for passage in words for text,confidence in passage)
            raw_query=query_attributes(self.families.attributes,raw_text)
            details['raw_query']={k:sorted(v) for k,v in raw_query.items()}
            details['reliable_query']={k:sorted(query.get(k,())) for k in KEYS}
            if len(raw_query['grape'])>1 or any(len(query.get(k,()))>1 for k in KEYS):return abstain('raw_blend_or_reliable_conflict_uncertainty')
            contenders=self.title_catalog.contenders(int(base_order[0]),base_order,query);details['contenders']=contenders
            if contenders['unknown']:return abstain('compatible_unknown_metadata_or_catalog_title')
            if not self.title_gallery.ready(contenders['known']):return abstain('missing_or_duplicate_physical_reference_title_gallery')
            acquired=acquire_title(image,self.ocr_assets,self.families.attributes.vocab,script_text=raw_text)
            details['query_acquisition']=acquired
            if not acquired.get('accepted'):return abstain('no_reliable_complete_query_title_row')
            # Geometry locates text globally, but the original central detector
            # remains the identity of the selected bottle. Other bottles cannot
            # supply an accepted anchor or title context.
            x1,y1,x2,y2=central_box
            for box in [acquired['anchor']['ink_box'],acquired['following_row']['ink_box'],acquired['box']]:
                if not (x1<=box[0]<box[2]<=x2 and y1<=box[1]<box[3]<=y2):return abstain('query_title_or_anchor_outside_original_central_bottle')
            crop=image.crop(acquired['box']).convert('RGB')
            if acquired.get('angle_degrees'):crop=crop.rotate(acquired['angle_degrees'],Image.Resampling.BICUBIC,expand=True,fillcolor=(255,255,255))
            feature_started=time.perf_counter();details['model_calls']=1
            feature=self.engine.model.so_embedder.features([crop])[0]
            details['feature_wall_ms']=1000*(time.perf_counter()-feature_started)
            scores=self.title_gallery.score(feature,contenders['known'])
            selected,decision=title_decision(base_order,order,query,self.title_catalog,acquired,scores,self.title_gallery.proofs,raw_multi_grape=False)
            details.update(decision,reference_proofs={str(i):self.title_gallery.proofs[i] for i in contenders['known']})
            return selected,details
        except Exception as exc:
            details['errors'].append({'phase':'title_verification','type':type(exc).__name__,'message':str(exc)})
            return abstain('title_verification_error_preserve_c08')
        finally:
            details['returned_wall_ms']=1000*(time.perf_counter()-started);details['drained_wall_ms']=details['returned_wall_ms']

    def close(self):
        self.ocr_pool.shutdown(wait=True);self.core._POOL.shutdown(wait=True)
