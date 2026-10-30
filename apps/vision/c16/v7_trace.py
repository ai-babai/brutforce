"""C15 adapter: request-scoped fail-open trace, frozen ranking helpers."""
import ast,contextvars,hashlib,json,math,os,platform,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from workflow_trace import WorkflowPredictor as Base,RequestTrace,clean,sha,LOG
from constraint_runtime import ConstraintBoost
from semantic_evidence import VERSION as UNICODE_EVIDENCE_VERSION
HERE=Path(__file__).resolve().parent
RELEASE=json.loads((HERE/'release.json').read_text())
OBSERVER=contextvars.ContextVar('c09_request_observer',default=None)

def qualification_overlay(release,runtime):
    """Serving readback overlay; native frozen recipe status is kept separately.

    The receipt is root transaction output after all three effective API checks.
    It attests that readback instant, not a perpetual live process check.
    """
    base={'source':'qualification_overlay','status':'QUALIFIED_READY_FOR_ACTIVATION' if release.get('qualified') is True else 'DEVELOPMENT_UNQUALIFIED','release':release['version'],'activation_checked':False,'active_readback_instant_only':True}
    path=Path(runtime)/'SERVING-ACTIVATION.json'
    if not path.is_file():return base
    try:
        doc=json.loads(path.read_text());binding=doc['qualification_binding'];actual=doc['actual_activation']
        for key in ('release_version','candidate_freeze_sha256','candidate_bundle_sha256','nomination_freeze_sha256'):
            expected={'release_version':release['version'],'candidate_freeze_sha256':release['freeze_sha256'],'candidate_bundle_sha256':release['candidate_bundle_sha256'],'nomination_freeze_sha256':release.get('nomination_freeze_sha256')}[key]
            if binding.get(key)!=expected:raise ValueError('Activation identity differs')
        if release.get('qualified') is not True or not release.get('nomination_freeze_sha256'):raise ValueError('No qualified nominee')
        if not binding.get('qualification_receipt_sha256') or not binding.get('deployment_intent_sha256'):raise ValueError('Missing qualification/intent source binding')
        if actual.get('status')!='PASS' or sha(Path(runtime)/'ACTUAL-ACTIVATION.json')!=doc['actual_activation_sha256']:raise ValueError('Activation receipt pin differs')
        if json.loads((Path(runtime)/'ACTUAL-ACTIVATION.json').read_text())!=actual:raise ValueError('Activation evidence bytes differ')
        if doc.get('status')!='ACTIVATED_READBACK_VERIFIED':raise ValueError('Activation revoked/pending')
        health=actual['candidate_health']
        if health.get('model_version')!=release['serving']['model_version'] or health.get('index_version')!=release['serving']['serving_index_version'] or health.get('threads')!=2 or health.get('ort_threads')!=6 or health.get('workflow_trace')!=1:raise ValueError('Actual candidate readback differs')
        apis=actual['effective_apis']
        if set(apis)!={'brutforce-prod.service','brutforce-test.service','brutforce-demo.service'}:raise ValueError('Activation API scope differs')
        for unit,item in apis.items():
            env=item['effective_binding']
            if item.get('startup_identity_verified') is not True or int(item.get('pid',0))<=0 or not item.get('actual_executable_sha256'):raise ValueError('API executable identity not verified')
            if env.get('VISION_SERVICE_URL')!='http://127.0.0.1:'+str(release['serving_port']) or env.get('VISION_INDEX_VERSION')!=release['serving']['serving_index_version']:raise ValueError('API serving identity differs')
            if unit.endswith('demo.service'):
                if env.get('RECOMMENDATION_INDEX_FILE') or env.get('RECOMMENDATION_INDEX_SHA256'):raise ValueError('DEMO mode differs')
            elif item.get('recommendation_sha256')!=env.get('RECOMMENDATION_INDEX_SHA256'):raise ValueError('Recommendation binding absent')
        return dict(base,status='QUALIFIED_ACTIVE',activation_checked=True,receipt_path=str(path),receipt_sha256=sha(path),actual_activation_sha256=doc['actual_activation_sha256'],qualification_receipt_sha256=binding['qualification_receipt_sha256'],deployment_intent_sha256=binding['deployment_intent_sha256'])
    except Exception as exc:return dict(base,activation_checked=True,activation_error=type(exc).__name__,active=False)

def ast_equivalence_receipt(source_path):
    """Execute frozen instrument's verification prefix, without runtime exec.

    This runs its actual insertion, anchor and strip/equality checks. The
    original recognition source is parsed only: no model/runtime imports occur.
    """
    helper=HERE/'workflow_trace.py'
    definition=next(n for n in ast.parse(helper.read_text()).body
                    if isinstance(n,ast.FunctionDef) and n.name=='instrument')
    stop=next(i for i,n in enumerate(definition.body) if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='module' for t in n.targets))
    definition.body=definition.body[:stop]
    definition.name='_verify_ast'
    definition.body.append(ast.parse("return {'original_dump': original_dump, 'stripped_dump': ast.dump(check, include_attributes=False), 'anchors': hits}").body[0])
    tree=ast.fix_missing_locations(ast.Module(body=[definition],type_ignores=[]))
    scope={'ast':ast,'Path':Path}
    exec(compile(tree,'<frozen-instrument-verification-prefix>','exec'),scope)
    result=scope['_verify_ast'](source_path)
    digest=lambda text:hashlib.sha256(text.encode()).hexdigest()
    return {'verified':True,'method':'executed_frozen_instrument_AST_insert_strip_exact_equality_prefix',
            'runtime_executed':False,'recognition_source_sha256':sha(source_path),
            'workflow_trace_source_sha256':sha(helper),
            'verification_prefix_ast_sha256':digest(ast.dump(tree,include_attributes=False)),
            'original_ast_sha256':digest(result['original_dump']),
            'stripped_ast_sha256':digest(result['stripped_dump']),
            'anchor_hits':result['anchors']}

class Tee:
    def __init__(self,primary,trace):
        self.primary,self.trace=primary,trace;self.capture_errors=primary.capture_errors
    def capture(self,name,values):
        self.primary.capture(name,values)
        try:self.trace.capture(name,values)
        except Exception as exc:
            self.trace.capture_errors.append({'stage':name,'error':type(exc).__name__})
            LOG.exception('C09 diagnostic observation failed')

class ObservedCore:
    def __init__(self,core):self.core=core;self._POOL=core._POOL
    def predict(self,*args,**kwargs):
        trace=OBSERVER.get()
        if trace is not None:kwargs['_workflow_observer']=Tee(kwargs['_workflow_observer'],trace)
        return self.core.predict(*args,**kwargs)

class V7Trace(RequestTrace):
    def render(self):
        super().render()
        for event in self.doc['events']:
            if event['stage']=='result':event['stage']='baseline_result'
            if event['stage']=='fusion':
                event['decisions']['ocr']={'status':'deferred','reason':'original cascade proposal; C08 evidence follows'}
                event['decisions']['catalog_text']={'status':'deferred','reason':'semantic and frozen V6 visual family gates follow'}
        final=getattr(self,'final',None)
        if final is None:return
        ev=final.get('evidence',{})
        self.doc['events'].append({'stage':'C08 coherent-gallery proposal and verification',
            'at_ms':round(1000*(time.perf_counter()-self.started),3),'evidence':clean(ev),
            'rules':{'baseline':'original SIMPLE84 cascade; originalTop20 membership observationally checked below',
                     'visual_proposal':'legacy V6 visual decision retained by default; current-gallery distinct-crop majority is only a nomination',
                     'coherent_nomination_verification':'eligible current-gallery nomination, original Top5 and structural family, exact single raw catalog grape uniquely supports known candidate; reliable known conflicts block promotion; raw word confidence unchanged',
                     'visual_override_provenance':'consensus_override describes legacy V6 proposal; coherent_support_override describes separately verified current-gallery nomination',
                     'visual_family_scope':'frozen V6 CatalogFamilies',
                     'semantic_family_scope':'retained C05 Top5 text verification; separate C08 structured-family original Top20 generation with unknown-kind compatibility',
                     'semantic_descriptor_acquisition':'only unresolved raw descriptor nomination; selected-bottle text components and symmetric half/full glyph-height borders, at most4calls/550ms; physical-row transforms correlated',
                     'Unicode_descriptor_evidence':'only outer UnicodeP punctuation separated and retained; internal punctuation/digits/symbols rejected; complete exact global color/sugar token, >=5 alphabetic glyphs each>=90, monotonic centers, bounded overlap/merged/degenerate boxes, original word bounds and actual ink; raw word confidence retained separately',
                     'semantic_verification':'preserve C05 output by default; uniformly select anywhere originalTop20;  reliable grape or both color+sugar must contradict current head, fully support exactly one related originalTop20 candidate, and leave no compatible unknown-metadata competitor',
                     'reliable_word_OCR':'confidence >=90 once or >=80 in both fixed ROIs',
                     'semantic_selection':'reject reliable known-field contradictions; unknown fields compatible; earliest original compatible Top5 when current head contradicts',
                     'character_fallback':'character-v2 only for unresolved known grape ambiguity, no word text_override; >=5 maximal contiguous alphabetic characters each >=90, strict geometry, exact unique global grape alias, related-family known grape support',
                     'character_budget':'550ms, at most4 OCR calls, bounded foreground/components/merge work; deadline/partial state retained',
                     'word_and_character_confidence':'separate actual provenance; never fabricate whole-word confidence',
                     'raw_contradictions':'reliable word/character disagreement cannot promote',
                     'raw_blend_uncertainty':'multiple exact raw grape phrases suppress an incomplete reliable grape subset; reliable color/sugar constraints retained; no fuzzy/partial/shortcode mappings'}})
        baseline=next((e['output'] for e in self.doc['events'] if e['stage']=='baseline_result'),{})
        indices=ev.get('original_base_top20',[])[:5]
        if not indices:indices=[self.owner.slug_index[s] for s in baseline.get('ranked_slugs',[])[:5]]
        original_slugs=baseline.get('ranked_slugs',[])[:5]
        evidence_slugs=[str(self.owner.engine.slugs[int(i)]) for i in indices]
        final_slugs=final.get('ranked_slugs',[])[:5]
        checked=bool(original_slugs and final_slugs)
        preserved=bool(checked and len(original_slugs)==len(final_slugs)
                       and len(set(original_slugs))==len(original_slugs)
                       and set(original_slugs)==set(final_slugs)
                       and evidence_slugs==original_slugs)
        all_indices=ev.get('original_base_top20',[])[:20]
        if not all_indices:all_indices=[self.owner.slug_index[s] for s in baseline.get('ranked_slugs',[])[:20]]
        original20=baseline.get('ranked_slugs',[])[:20]
        evidence20=[str(self.owner.engine.slugs[int(i)]) for i in all_indices]
        final20=final.get('ranked_slugs',[])[:20]
        scope_checked=bool(original20 and final20)
        top20_preserved=bool(scope_checked and len(original20)==len(final20) and len(set(original20))==len(original20) and set(original20)==set(final20) and original20==evidence20)
        expansion=ev.get('semantic_expansion',{});title=ev.get('title_verification',{})
        title_used=bool(title.get('title_override'));selected=title.get('selected_candidate') if title_used else expansion.get('selected_candidate')
        selected_slug=str(self.owner.engine.slugs[int(selected)]) if selected is not None else None
        resource=ev.get('resource_field_verification',{});upper=ev.get('upper_view_verification',{})
        new_channel=None;new_verified_metadata=False
        if ev.get('resource_signature_override'):
            signature=resource.get('positive_signature',{});selected=signature.get('selected_index')
            new_channel='complete_positive_product_color_signature'
            new_verified_metadata=bool(signature.get('override') and signature.get('unknown_membership_retained') is True and signature.get('word90_proofs'))
        elif ev.get('upper_view_override'):
            selection=upper.get('selection',{});selected=selection.get('selected_candidate')
            new_channel='source_bound_upper_bottle_visual_verification'
            new_verified_metadata=bool(selection.get('override') and selection.get('original_top20_preserved') is True and upper.get('acquisition',{}).get('accepted') is True)
        elif ev.get('upper_artwork_override'):
            appearance=upper.get('pairwise_artwork',{});selected=appearance.get('nominated_index')
            new_channel='correlated_upper_visual_nomination_pairwise_artwork'
            new_verified_metadata=bool(appearance.get('override') and appearance.get('originalTop20_membership_preserved') is True and appearance.get('global_hue_uniqueness_asserted') is False)
        selected_slug=str(self.owner.engine.slugs[int(selected)]) if selected is not None else None
        verified_selection=bool((title_used or expansion.get('expansion_override') or (new_channel and new_verified_metadata)) and top20_preserved and selected in all_indices and final_slugs and final_slugs[0]==selected_slug)
        verified_extension=bool(verified_selection and selected not in indices)
        observed_scope='original_top20_extension' if verified_extension else ('original_top5' if verified_selection else None)
        membership_changed=bool(checked and set(original_slugs)!=set(final_slugs))
        scope_metadata_matches=bool(verified_selection and ((title_used and title.get('original_top20_preserved') is True and title.get('model_calls')==1 and title.get('query_acquisition',{}).get('proof_contract')=='query_reliable_whole_grape' and title.get('reference_proofs')) or (not title_used and expansion.get('verified_scope')==observed_scope and expansion.get('candidate_scope_extended')==verified_extension and expansion.get('original_top5_membership_changed')==membership_changed)))
        if new_channel:scope_metadata_matches=bool(verified_selection and new_verified_metadata)
        self.doc['events'].append({'stage':'C09 original candidate scope observation',
            'check_performed':checked,'original_top5_preserved':preserved,
            'original_top5_slugs':original_slugs,'evidence_original_top5_slugs':evidence_slugs,
            'final_top5_slugs':final_slugs,'original_top20_checked':scope_checked,
            'original_top20_preserved':top20_preserved,'original_top20_slugs':original20,
            'evidence_original_top20_slugs':evidence20,'final_top20_slugs':final20,
            'semantic_verification_observed':verified_selection,'semantic_extension_observed':verified_extension,
            'selected_verified_slug':selected_slug,'verified_scope_observed':observed_scope,
            'independent_title_verification_observed':bool(title_used and verified_selection and scope_metadata_matches),
            'verification_channel':new_channel if new_channel else ('independent_title_region' if title_used else ('reliable_semantic_fields' if verified_selection else None)),
            'original_top5_membership_changed_observed':membership_changed,'verified_metadata_matches_observation':scope_metadata_matches,
            'status':('verified_semantic_reorder_in_original_top5' if verified_selection and scope_metadata_matches else 'verified_top5_preservation') if preserved else ('verified_original_top20_semantic_extension' if verified_extension and scope_metadata_matches else ('scope_violation' if checked else 'not_verifiable')),
            'effect':'diagnostic_only_result_unmodified'})
        head=int(indices[0]) if indices else None;rows=[]
        for pos in all_indices:
            pos=int(pos);slug=str(self.owner.engine.slugs[pos])
            rows.append({'index_row':pos,'slug':slug,'catalog':self.owner.references.get(slug,{}),
                         'attributes':{k:sorted(v) for k,v in self.owner.candidate.families.attributes.rows[pos].items()},
                         'semantic_related_to_original_head':bool(head is not None and self.owner.candidate.families.same(head,pos)),
                         'visual_related_to_original_head':bool(head is not None and self.owner.candidate.visual_families.same(head,pos)),
                         'expansion_related_to_original_head':bool(head is not None and self.owner.candidate.expansion_families.same(head,pos))})
        self.doc['events'].append({'stage':'C08 candidate metadata and family scopes','candidates':clean(rows),
                                  'semantic_text_gate':ev.get('semantic_text_gate'),
                                  'visual_text_gate':ev.get('visual_text_gate')})
        self.doc['events'].append({'stage':'C08 visual nomination and raw varietal verification',
            'legacy_visual_decision':clean(ev.get('legacy_visual_decision')),
            'coherent_visual_nomination':clean(ev.get('coherent_visual_nomination')),
            'coherent_verification':clean(ev.get('coherent_verification')),
            'consensus_override':ev.get('consensus_override'),
            'coherent_support_override':ev.get('coherent_support_override'),
            'raw_ocr_words_with_measured_confidence':clean(ev.get('ocr_words',[])),
            'raw_query':clean(ev.get('raw_query',{})),
            'raw_multi_grape_uncertainty':bool(ev.get('raw_multi_grape_uncertainty',False)),
            'suppressed_grape_query':clean(ev.get('suppressed_grape_query',[])),
            'final_trusted_query':clean(ev.get('query',{}))})
        if 'character_ocr' in ev:
            self.doc['events'].append({'stage':'C08 supplemental character OCR',
                                      'evidence':clean(ev['character_ocr']),
                                      'family_gate':ev.get('character_family_gate'),
                                      'trusted_query':clean(ev.get('character_query',{}))})
        self.doc['events'].append({'stage':'C08 bounded semantic acquisition and verified selection',
            'acquisition_gate':ev.get('semantic_acquisition_gate'),
            'acquisition':clean(ev.get('semantic_acquisition',{})),
            'verification':clean(ev.get('semantic_expansion',{})),
            'expansion_override':bool(ev.get('semantic_expansion_override',False)),
            'word_character_confidence_relation':'separate measured evidence; physical-row transforms do not create independent votes'})
        self.doc['events'].append({'stage':'C09 bounded title acquisition and independent verification','evidence':clean(ev.get('title_verification',{})),'title_override':bool(ev.get('title_override',False)),'retrieval_scope':'existing_original_top20_only; missing/unknown compatible contenders block','confidence_relation':'measured whole-word/glyph evidence separate from existing-encoder image scores; correlated physical transforms are not independent votes'})
        self.doc['events'].append({'stage':'C13 bounded local whole-token reacquisition and original-policy verification','evidence':clean(ev.get('local_grape_verification',{})),'local_grape_override':bool(ev.get('local_grape_override',False)),'confidence_contract':'actual same-process float TSVword90 and original character90 geometry distinct; rejected character geometry preserved; correlated rows are not independent votes','image_contract':'original visual/detection/title images unchanged; optional text canvas explicitly source mapped'})
        self.doc['events'].append({'stage':'C14 bounded resource observation and positive identity verification',
            'evidence':clean(ev.get('resource_field_verification',{})),
            'positive_signature_override':bool(ev.get('resource_signature_override',False)),
            'contract':'actual lexical word/glyph confidence retained; unverified acquired fields never constrain upper candidates; complete genuine product+color word90 signature only, unknown membership retained'})
        self.doc['events'].append({'stage':'C14 source-bound upper-view nomination and verification',
            'evidence':clean(ev.get('upper_view_verification',{})),
            'upper_view_override':bool(ev.get('upper_view_override',False)),
            'upper_artwork_override':bool(ev.get('upper_artwork_override',False)),
            'retrieval_scope':'originalTop20, every compatible unknown source ready and scored; pairwise nomination additionally originalTop5',
            'contract':'one existing encoder call; same physical upper RGB crop correlated artwork; no complete-cap, wine-colour or global hue uniqueness assertion; inline actual detector/quality observation SHA retained'})
        self.doc['events'].append({'stage':'C15 positive context-title acquisition and verification',
            'evidence':clean(ev.get('context_title_verification',{})),
            'independent_timeout_recovery':clean(ev.get('resource_field_verification',{}).get('independent_timeout_recovery',{})),
            'context_title_override':bool(ev.get('context_title_override',False)),
            'retrieval_scope':'same-producer related-variety compatible contenders within originalTop20; every required reference must be ready',
            'contract':'complete positive title observation, reliable whole grape; generic specificity is uncertainty, absent Reserve is never negative evidence; failed/incomplete acquisition preserves incoming C14',
            'physical_evidence':'same selected bottle axis and measured context; transformed rows remain correlated',
            'confidence_contract':'measured glyph confidence90 distinct from existing SigLIP cosine70/margin05; no invented word confidence'})
        self.doc['events'].append({'stage':'serving qualification overlay','evidence':clean(ev.get('qualification_overlay',{})),'native_recipe_status':ev.get('native_recipe_qualification')})
        self.doc['events'].append({'stage':'final_result','output':clean(final)})
        self.doc['unused_stages']={'OCR':'used' if ev.get('ocr_used') else 'not consumed; crop/family gate false',
                                  'semantic_acquisition':'used' if 'semantic_acquisition' in ev else 'not consumed; unresolved descriptor gate false',
                                  'character_OCR':'used' if 'character_ocr' in ev else 'not consumed; fallback gate false',
                                  'OWL':'not called by C08','wine_class_gate':'not called by C08'}

class WorkflowPredictor(Base):
    def __init__(self,source,config_path,directory,engine,policy,identity,catalog,
                 catalog_path=None,ocr_assets_path=None):
        self.engine,self.policy=engine,policy
        self.config_path=Path(config_path);self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        assets_path=Path(ocr_assets_path or HERE/'OCR-ASSETS.json')
        assets=json.loads(assets_path.read_text())
        for path,expected in assets['files'].items():
            if sha(path)!=expected:raise ValueError('OCR asset pin mismatch: '+path)
        catalog_path=Path(catalog_path or '/srv/lct/data/vision-retrieval/20260925/detectors/catalog-audit/catalog-bundle.json')
        receipt=ast_equivalence_receipt(source)
        self.candidate=ConstraintBoost(engine,policy,catalog_path,assets,source)
        self.http_lock=threading.RLock();self.actual_word_futures=[]
        original_start=self.candidate.start_ocr
        def observed_start(image,box):
            submitted=time.perf_counter();records=self.actual_word_futures
            body_box,jobs=original_start(image,box)
            for number,job in enumerate(jobs):
                roi=list(body_box)
                if number==1:roi[1]+=math.floor(.60*(roi[3]-roi[1]))
                record={'pass_index':number,'input_box':roi,'status':'submitted',
                        'source':'original_frozen_start_ocr_future',
                        'timing_scope':'submission_including_original_ROI_preparation_to_future_completion'}
                records.append(record)
                def finished(future,record=record):
                    record['submission_to_completion_ms']=round(1000*(time.perf_counter()-submitted),3)
                    if future.cancelled():record['status']='cancelled_before_execution';return
                    try:record.update(status='ok',words=clean(future.result()))
                    except Exception as exc:record.update(status='error',error_type=type(exc).__name__)
                job.add_done_callback(finished)
            return body_box,jobs
        self.candidate.start_ocr=observed_start
        receipt_path=self.directory/('AST-EQUIVALENCE-'+receipt['recognition_source_sha256']+'.json')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        self.candidate.core=ObservedCore(self.candidate.core)
        self.references={r['slug']:r for r in catalog['references']}
        self.slug_index={str(s):i for i,s in enumerate(engine.slugs)}
        helpers=json.loads((HERE/'CANDIDATE-SOURCE-PINS.json').read_text())
        self.identity=dict(identity,name='Boost V16 C16',policy_name=RELEASE['candidate_id'],
            release=RELEASE['version'],qualification=RELEASE['status'],freeze_sha256=RELEASE['freeze_sha256'],
            candidate_bundle_sha256=RELEASE['candidate_bundle_sha256'],tracer_version='c16-independent-positive-recovery-scope-observer-v1',
            recognition_source_sha256=sha(source),candidate_runtime_sha256=helpers['constraint_runtime.py'],
            candidate_policy_sha256=helpers['candidate_policy.py'],visual_policy_sha256=helpers['constraint_policy.py'],
            character_acquisition_sha256=helpers['character_acquisition.py'],character_evidence_sha256=helpers['character_evidence.py'],
            unicode_descriptor_evidence_version=UNICODE_EVIDENCE_VERSION,expanded_policy_sha256=helpers['expanded_policy.py'],semantic_acquisition_sha256=helpers['semantic_acquisition.py'],
            semantic_evidence_sha256=helpers['semantic_evidence.py'],candidate_source_pins=helpers,adapter_source_sha256=sha(__file__),policy_source_sha256=helpers['candidate_policy.py'],
            policy_sha256=helpers['candidate_policy.py'],ast_equivalence_verified=bool(receipt['verified'] and receipt_path.exists()),
            ast_equivalence_receipt_path=str(receipt_path),ast_equivalence_receipt_sha256=sha(receipt_path),
            ast_equivalence_receipt=receipt,weights_unchanged=True,
            upper_gallery_binding=self.candidate.upper_gallery.assets,artwork_gallery_binding=self.candidate.artwork_gallery.assets,
            frozen_helper_count=40,derived_asset_count=8,existing_encoder_upper_calls_bound=1,
            context_title_gallery_binding=self.candidate.context_title_gallery.assets,existing_encoder_context_title_calls_bound=1,
            title_gallery_binding=self.candidate.title_gallery.assets,title_verification_scope='existing_originalTop20_only',
            derived_title_assets=json.loads((HERE/'DERIVED-ASSET-PINS.json').read_text()),existing_encoder_title_calls_bound=1,new_models=False,
            index_assets_unchanged=True,host=platform.node(),pid=os.getpid(),hot_trace_config=str(self.config_path))
    def qualification_status(self):return qualification_overlay(RELEASE,self.directory.parent)
    def predict(self,content,catalog_version,index_version,request=None):
        with self.http_lock:
            self.actual_word_futures=[]
            return self._predict_with_trace(content,catalog_version,index_version,request)
    def drain_request(self):
        started=time.perf_counter()
        # Complete uncancellable speculative OCR/detector work in this request.
        # Shutdown waits callbacks too; queue sentinels alone do not drain2workers.
        self.candidate.ocr_pool.shutdown(wait=True)
        self.candidate.ocr_pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='c09-http-ocr')
        self.candidate.core._POOL.submit(lambda:None).result()
        return round(1000*(time.perf_counter()-started),3)
    def _predict_with_trace(self,content,catalog_version,index_version,request=None):
        observer=V7Trace(self,content,request or {}) if self.enabled() else None
        token=OBSERVER.set(observer)
        try:
            result=self.candidate.predict(content,catalog_version,index_version)
            result.setdefault('timings_ms',{})['http_request_drain_ms']=self.drain_request()
            for record in self.actual_word_futures:
                record['candidate_consumption']=('title_auxiliary_conflict_check' if result.get('evidence',{}).get('title_only_word_acquisition') else 'word_decision') if result.get('evidence',{}).get('ocr_used') else 'prefetched_not_consumed'
            evidence=result.setdefault('evidence',{})
            evidence['native_recipe_qualification']=evidence.get('qualification')
            overlay=qualification_overlay(RELEASE,self.directory.parent)
            evidence['qualification_overlay']=overlay;evidence['qualification']=overlay['status']
            self.identity['qualification']=overlay['status'];self.identity['qualification_overlay']=overlay
            result.setdefault('evidence',{})['actual_word_futures']=clean(self.actual_word_futures)
            result['evidence']['cross_request_ocr_carryover']=False
            result['boost']['base_policy']=self.policy['name'];result['boost']['policy']=RELEASE['candidate_id']
            result.update(catalog_version=catalog_version,index_version=index_version,
                          model_version=self.identity['model_version'],serving_profile=self.identity['serving_profile'],
                          track=(request or {}).get('track','service'))
            if observer:observer.final=result
        except Exception as exc:
            self.drain_request()
            if observer:observer.doc['actual_word_futures']=clean(self.actual_word_futures)
            if observer:exc.workflow_trace_id=observer.finish(error={'type':type(exc).__name__,'message':str(exc)[:500]})
            raise
        finally:OBSERVER.reset(token)
        return result,observer.finish(result=result) if observer else None
    def close(self):self.candidate.close()
