"""Request-scoped observation of pinned SIMPLE84; no extra model inference.

The source AST is unchanged apart from guarded observation calls and an optional
observer argument. The original model, galleries, policy and sorting execute as-is.
"""
import ast
import datetime
import hashlib
import json
import logging
import math
import os
import platform
import time
import types
import uuid
from pathlib import Path

LOG = logging.getLogger('workflow_trace')
SCHEMA = 'wine-workflow/1'
TRACER_VERSION = 'simple84-observer-v1'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def _emit(observer, name, values):
    try:
        observer.capture(name, values)
    except Exception as exc:
        observer.capture_errors.append({'stage': name, 'error': type(exc).__name__})
        LOG.exception('Workflow observation failed: %s', name)

def instrument(path):
    """Fail at startup on unexpected source shape; never monkey-patch imports."""
    source = Path(path).read_text()
    tree = ast.parse(source, filename=str(path))
    original_dump = ast.dump(tree, include_attributes=False)
    predict = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'predict')
    predict.args.kwonlyargs.append(ast.arg(arg='_workflow_observer'))
    predict.args.kw_defaults.append(ast.Constant(None))
    anchors = {
        "stage['decode_ms'] = round(1000 * (time.perf_counter() - started))": 'decode',
        "stage['rank_ms'] += round(1000 * (time.perf_counter() - step))": 'view',
        'crop_needed = needs_crops(final_scores)': 'crop_gate',
        "encode('central_pad25', view_box(image, central, 'central_pad25'))": 'detector',
        "final_scores = cascade84(scores['fullframe'], scores['central_pad25'], legacy_scores)": 'fusion',
        'detector.cancel()': 'detector_unused',
        'return result': 'result',
    }
    hits = dict.fromkeys(anchors, 0)
    injected = []
    class Insert(ast.NodeTransformer):
        def visit(self, node):
            node = super().visit(node)
            if not isinstance(node, ast.stmt):
                return node
            text = ast.unparse(node)
            # rank timing exists twice: only the nested encode has view data.
            if text not in anchors or (anchors[text] == 'view' and getattr(node, 'lineno', 0) > encode_end):
                return node
            hits[text] += 1
            event = anchors[text]
            hook = ast.parse(f"if _workflow_observer is not None:\n    _workflow_emit(_workflow_observer, '{event}', locals())").body[0]
            injected.append(hook)
            ast.copy_location(hook, node)
            return [hook, node] if event in ('detector', 'result') else [node, hook]
    encode_node = next(n for n in predict.body if isinstance(n, ast.FunctionDef) and n.name == 'encode')
    encode_end = encode_node.end_lineno
    Insert().visit(predict)
    if any(n != 1 for n in hits.values()):
        raise ValueError('Workflow source anchors differ: ' + repr(hits))
    # Independently strip instrumentation and assert exact original AST.
    import copy
    check = copy.deepcopy(tree)
    class Strip(ast.NodeTransformer):
        def visit_If(self, node):
            if ast.unparse(node.test) == '_workflow_observer is not None':
                return None
            return self.generic_visit(node)
    Strip().visit(check)
    cp = next(n for n in check.body if isinstance(n, ast.FunctionDef) and n.name == 'predict')
    cp.args.kwonlyargs.pop(); cp.args.kw_defaults.pop()
    if ast.dump(check, include_attributes=False) != original_dump:
        raise ValueError('Workflow instrumentation changed recognition AST')
    module = types.ModuleType('workflow_simple84_core')
    module.__file__ = str(path)
    module.__dict__['_workflow_emit'] = _emit
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), module.__dict__)
    return module

def clean(value):
    """Strict JSON; nonfinite diagnostic scores are represented as null."""
    import numpy as np
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

class RequestTrace:
    def __init__(self, owner, content, request):
        self.owner = owner
        self.content = content
        self.started = time.perf_counter()
        now = datetime.datetime.now(datetime.timezone.utc)
        self.day = now.strftime('%Y-%m-%d')
        self.id = now.strftime('%Y%m%dT%H%M%S.%fZ-') + uuid.uuid4().hex[:12]
        self.events = []
        self.capture_errors = []
        self.doc = {'schema': SCHEMA, 'trace_id': self.id, 'started_at_utc': now.isoformat(),
                    'solution': owner.identity, 'request': request,
                    'input': {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)},
                    'events': self.events, 'observation_errors': self.capture_errors}

    def summary(self, scores):
        import numpy as np
        rank = np.argsort(-scores)
        valid = [int(i) for i in rank if np.isfinite(scores[i])]
        margin = float(scores[rank[0]] - scores[rank[1]]) if len(rank) >= 2 else None
        return {'margin': margin, 'finite_candidates': len(valid),
                'top20': [dict(self.owner.references.get(self.owner.engine.slugs[i], {}),
                               index_row=i, slug=self.owner.engine.slugs[i], cosine=float(scores[i]))
                          for i in valid[:20]]}

    def capture(self, name, v):
        # Store actual computed arrays by reference; format after CV completes.
        event = {'stage': name, 'at_ms': round(1000 * (time.perf_counter() - self.started), 3)}
        if name == 'decode':
            image, source = v['image'], v['source']
            event['output'] = {'source_format': source.format, 'source_size': list(source.size),
                               'source_mode': source.mode, 'exif_orientation': source.getexif().get(274),
                               'decoded_size': list(image.size), 'decoded_mode': image.mode,
                               'operation': 'EXIF transpose then RGB'}
        elif name == 'view':
            event.update(view=v['view'], box=list(v['box']),
                         _feature=v['features'][v['key']], _scores=v['scores'][v['view']],
                         gallery='Batch32 full', metadata_used_for_ranking=False)
        elif name == 'crop_gate':
            event.update(_scores=v['final_scores'], execute_crops=bool(v['crop_needed']),
                         rule='fullframe Top1-Top2 margin <= 0.05', threshold=0.05)
        elif name == 'detector':
            event.update(output=clean(v['boxes']), selected_box=list(v['central']),
                         fallback=not bool(v['boxes']), elapsed_ms=v['stage']['detect_ms'],
                         rule='nearest normalized geometric centre; confidence tie-break; fullframe fallback')
        elif name == 'fusion':
            event.update(_full=v['scores']['fullframe'], _pad25=v['scores']['central_pad25'],
                         _label=v['legacy_scores'], _selected=v['final_scores'],
                         legacy_gallery=v['policy']['gallery_sources']['legacy_label'])
        elif name == 'detector_unused':
            event.update(status='speculative_result_not_consumed',
                         cancelled=v['detector'].cancelled(),
                         reason='fullframe margin passed; no waiting for unused detector')
        elif name == 'result':
            event.update(output=clean(v['result']))
        self.events.append(event)

    def render(self):
        import numpy as np
        from boost_policy import top_margin
        rendered = []
        for raw in self.events:
            e = {k: v for k, v in raw.items() if not k.startswith('_')}
            if '_feature' in raw:
                f = raw['_feature']
                e['embedding'] = {'shape': list(f.shape), 'dtype': str(f.dtype),
                                  'norm': float(np.linalg.norm(f)),
                                  'sha256': hashlib.sha256(f.tobytes()).hexdigest()}
            if '_scores' in raw:
                e['ranking'] = self.summary(raw['_scores'])
            if raw['stage'] == 'fusion':
                fs, bs, ls = raw['_full'], raw['_pad25'], raw['_label']
                fr, br, lr = (np.argsort(-s) for s in (fs, bs, ls))
                bottle = bool(fr[0] in br[:5] and top_margin(bs) >= top_margin(fs) and top_margin(bs) >= .03)
                base = bs if bottle else fs
                ir = np.argsort(-base)
                reciprocal = bool(ir[0] in lr[:5] and lr[0] in ir[:5])
                label = bool(reciprocal and top_margin(ls) >= top_margin(base) and top_margin(ls) >= 0)
                selected = ls if label else base
                if not np.array_equal(selected, raw['_selected'], equal_nan=True):
                    raise ValueError('Observed decision differs from original cascade')
                e['legacy_label_ranking'] = self.summary(ls)
                e['decisions'] = {
                    'pad25': {'full_winner_in_pad25_top5': bool(fr[0] in br[:5]),
                              'full_margin': top_margin(fs), 'crop_margin': top_margin(bs),
                              'floor': .03, 'switch': bottle},
                    'pad10_legacy_label': {'reciprocal_top5': reciprocal,
                                          'label_margin': top_margin(ls), 'current_margin': top_margin(base),
                                          'floor': 0, 'switch': label},
                    'selected_view': 'central_pad10_legacy_label' if label else ('central_pad25' if bottle else 'fullframe'),
                    'ocr': {'status': 'skipped', 'reason': 'SIMPLE84 has no OCR stage'},
                    'catalog_text': {'status': 'display_only', 'reason': 'not used by SIMPLE84 ranking'},
                }
                e['selected_ranking'] = self.summary(selected)
            rendered.append(e)
        self.doc['events'] = rendered
        self.doc['unused_stages'] = {'OCR': 'not part of SIMPLE84', 'OWL': 'not called by SIMPLE84',
                                     'wine_class_gate': 'not called by SIMPLE84'}

    def finish(self, result=None, error=None):
        begin = time.perf_counter()
        try:
            self.render()
            self.doc.update(status='error' if error else 'ok', result=clean(result), error=error,
                            prediction_and_capture_ms=round(1000 * (begin - self.started), 3))
            directory = self.owner.directory / self.day / self.id
            directory.mkdir(parents=True, mode=0o700)
            directory.chmod(0o700)
            # Original bytes allow reproducible crops without another upload.
            if self.content:
                (directory / 'input.image').write_bytes(self.content)
                (directory / 'input.image').chmod(0o600)
                self.doc['input']['saved_file'] = 'input.image'
            self.doc['trace_prepare_and_input_write_ms'] = round(1000 * (time.perf_counter() - begin), 3)
            target = directory / 'workflow.json'
            temp = directory / 'workflow.json.tmp'
            temp.write_text(json.dumps(clean(self.doc), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            temp.chmod(0o600); temp.replace(target)
            LOG.warning(json.dumps({'workflow_trace_id': self.id, 'image_sha256': self.doc['input']['sha256'],
                                    'solution': self.owner.identity['name'], 'path': str(target),
                                    'status': self.doc['status'],
                                    'trace_overhead_ms': round(1000 * (time.perf_counter() - begin), 3)}))
            return self.id
        except Exception:
            LOG.exception('Workflow trace persistence failed; recognition result preserved')
            return None

class WorkflowPredictor:
    def __init__(self, source, config_path, directory, engine, policy, identity, catalog):
        self.core = instrument(source)
        self.engine = engine
        self.policy = policy
        self.config_path = Path(config_path)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.identity = dict(identity, name='SIMPLE84 boost', tracer_version=TRACER_VERSION,
                             recognition_source_sha256=sha(source), tracer_source_sha256=sha(__file__),
                             ast_equivalence_verified=True, host=platform.node(), pid=os.getpid())
        self.references = {r['slug']: r for r in catalog['references']}

    def enabled(self):
        try:
            flag = json.loads(self.config_path.read_text())['workflow_trace']
            if type(flag) is not int or flag not in (0, 1):
                raise ValueError('workflow_trace must be 0 or 1')
            return bool(flag)
        except Exception:
            LOG.exception('Workflow config invalid; tracing remains enabled')
            return True

    def predict(self, content, catalog_version, index_version, request=None):
        observer = RequestTrace(self, content, request or {}) if self.enabled() else None
        try:
            result = self.core.predict(self.engine, content, self.policy, catalog_version, index_version,
                                       _workflow_observer=observer)
        except Exception as exc:
            if observer:
                observer.finish(error={'type': type(exc).__name__, 'message': str(exc)[:500]})
            raise
        trace_id = observer.finish(result=result) if observer else None
        return result, trace_id

    def rejection(self, error, content=b'', request=None):
        if not self.enabled():
            return None
        observer = RequestTrace(self, content, request or {})
        observer.events.append({'stage': 'HTTP admission', 'at_ms': 0, 'status': 'rejected', 'reason': error})
        return observer.finish(error=error)
