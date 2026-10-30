"""Source-bound derived upper-view vectors; reuse the verified existing encoder.

No model initialization, OCR, catalog image reads, or per-request asset hashes.
Query image/crop measurements and a single existing encoder call occur only
after every compatible reference, including unknown metadata, is ready.
"""
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import source_quality
from upper_geometry import VERSION as GEOMETRY_VERSION

VERSION = 'upper-gallery-loader-v1-existing-verified-encoder'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def native(value):
    if isinstance(value, np.ndarray):
        return native(value.tolist())
    if isinstance(value, np.generic):
        return native(value.item())
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [native(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('Unsupported actual detector observation type')


def inline_evidence(value):
    """Content-addressed actual JSON observation, explicitly not a saved file."""
    payload = native(value)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    digest = hashlib.sha256(encoded).hexdigest()
    return {'uri': 'inline:sha256:' + digest, 'sha256': digest,
            'storage': 'inline_actual_observation_not_persisted_file',
            'canonical_json': payload}


class UpperGallery:
    def __init__(self, folder, references, title_gallery, engine, *,
                 expected_manifest_sha256, expected_features_sha256):
        folder = Path(folder)
        self.manifest_path = folder / 'assets/upper-gallery.json'
        self.features_path = folder / 'assets/upper-gallery.npz'
        if sha(self.manifest_path) != expected_manifest_sha256:
            raise ValueError('Frozen upper manifest mismatch')
        if sha(self.features_path) != expected_features_sha256:
            raise ValueError('Frozen upper vectors mismatch')
        m = json.loads(self.manifest_path.read_text())
        self.manifest = m
        if m.get('version') != 'source_bound_upper_bottle_visual_top35-v6-model-crop-quality':
            raise ValueError('Unsupported upper gallery source contract')
        verified = title_gallery.assets
        binding = m['encoder_binding']
        old = verified.get('encoder', {})
        if verified.get('encoder_binding_verified') is not True:
            raise ValueError('Existing encoder has not been verified')
        if (len(binding.get('logical_files', {})) != 7 or
                any(binding.get(k) != old.get(k)
                    for k in ('logical_files', 'batch_shape', 'dtype', 'crop_transform'))):
            raise ValueError('Upper encoder differs from already verified title encoder')
        if m['catalog_sha256'] != title_gallery.manifest['catalog_sha256']:
            raise ValueError('Upper and verified title catalog differ')
        if m['features_sha256'] != expected_features_sha256:
            raise ValueError('Upper feature digest not bound by manifest')
        if not m.get('source_manifest_sha256'):
            raise ValueError('Missing reference acquisition lineage')
        self.embedder = engine.model.so_embedder
        # TitleGallery verified this loaded graph/processor at this engine init;
        # reusing its binding avoids a second graph/data/processor hash pass.
        self.binding_sha256 = inline_evidence(binding)['sha256']
        self.assets = {'version': VERSION, 'manifest_sha256': expected_manifest_sha256,
                       'features_sha256': expected_features_sha256,
                       'catalog_sha256': m['catalog_sha256'],
                       'source_manifest_sha256': m['source_manifest_sha256'],
                       'encoder_binding_sha256': self.binding_sha256,
                       'encoder_binding_verified': True,
                       'verification_reused_from': verified['manifest_sha256'],
                       'logical_encoder_files': dict(binding['logical_files'])}
        with np.load(self.features_path, allow_pickle=False) as data:
            if set(data.files) != {'features', 'catalog_indices'}:
                raise ValueError('Unexpected upper vector archive closure')
            matrix = data['features']
            indices = data['catalog_indices']
        if (matrix.dtype != np.float32 or matrix.ndim != 2 or
                indices.dtype != np.int64 or indices.ndim != 1 or
                len(indices) != len(matrix) or not np.isfinite(matrix).all()):
            raise ValueError('Invalid upper vector archive')
        ids = list(map(int, indices))
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate upper feature index')
        norms = np.linalg.norm(matrix, axis=1)
        if not np.isfinite(norms).all() or np.any(norms <= 0):
            raise ValueError('Invalid upper feature norm')
        self.dimension = matrix.shape[1]
        if self.dimension <= 0:
            raise ValueError('Empty upper feature dimensions')
        if any(len(v) != self.dimension for v in title_gallery.vectors.values()):
            raise ValueError('Existing encoder feature dimensions differ')
        self.vectors = {i: v / n for i, v, n in zip(ids, matrix, norms)}
        feature_rows = m['feature_rows']
        if len(feature_rows) != len(ids):
            raise ValueError('Manifest/archive row count mismatch')
        self.proofs = {}
        self.reference_rows = {}
        for offset, row in enumerate(feature_rows):
            i = row['catalog_index']
            if type(i) is not int or i != ids[offset] or row['vector_row'] != offset:
                raise ValueError('Manifest/archive vector order mismatch')
            if not 0 <= i < len(references):
                raise ValueError('Reference outside actual catalog')
            reference = references[i]
            geometry = row['geometry']
            quality = geometry.get('quality', {})
            measured = quality.get('measured', {})
            if (row['slug'] != reference['slug'] or
                    row['reference_sha256'] != reference['sha256'] or
                    geometry.get('accepted') is not True or
                    geometry.get('version') != GEOMETRY_VERSION or
                    geometry.get('source_sha256') != row['reference_sha256'] or
                    geometry.get('upper_rgb_crop_sha256') != row['view_crop_sha256'] or
                    geometry.get('box') != measured.get('box') or
                    measured.get('upper_rgb_crop_sha256') != row['view_crop_sha256'] or
                    quality.get('accepted') is not True or
                    quality.get('source_sha256') != row['reference_sha256'] or
                    quality.get('nomination', {}).get('accepted_nomination') is not True or
                    not all(quality.get('actual_checks', {}).get(k) is True for k in
                            ('full_bottle_model_aspect', 'dominant_model_height',
                             'dominant_model_area', 'visible_upper_crop_contrast')) or
                    not geometry.get('evidence_path') or not geometry.get('evidence_sha256') or
                    geometry.get('complete_cap_asserted') is not False):
                raise ValueError('Unbound source/geometry/feature row')
            proof = dict(row, catalog_sha256=m['catalog_sha256'],
                         encoder_binding_sha256=self.binding_sha256,
                         gallery_manifest_sha256=expected_manifest_sha256)
            proof['score_row_binding'] = {k: row[k] for k in
                                         ('catalog_index', 'slug', 'reference_sha256', 'view_crop_sha256')}
            self.proofs[i] = proof
            self.reference_rows[i] = {'slug': row['slug'], 'reference_sha256': row['reference_sha256']}
        unknown = m['unknown_rows']
        unknown_ids = [r['catalog_index'] for r in unknown]
        if len(set(unknown_ids)) != len(unknown_ids) or set(unknown_ids) & set(ids):
            raise ValueError('Unknown/reference row overlap')
        for row in unknown:
            i = row['catalog_index']
            if type(i) is not int or not 0 <= i < len(references) or row['slug'] != references[i]['slug']:
                raise ValueError('Unknown row catalog identity mismatch')
        self.unknown_rows = {r['catalog_index']: r for r in unknown}

    def readiness(self, candidates):
        ids = list(map(int, candidates))
        missing = [i for i in ids if i not in self.vectors or i not in self.proofs]
        crops = [self.proofs[i]['view_crop_sha256'] for i in ids if i in self.proofs]
        return {'ready': bool(ids) and len(ids) == len(set(ids)) and not missing and
                len(crops) == len(set(crops)), 'required_contenders': ids,
                'missing_or_unknown_references': missing,
                'duplicate_reference_crops': len(crops) != len(set(crops)),
                'all_unknown_metadata_competitors_required': True}

    def ready(self, candidates):
        return self.readiness(candidates)['ready']

    def score(self, feature, candidates):
        if not self.ready(candidates):
            raise ValueError('Every compatible reference must be ready before scoring')
        feature = np.asarray(feature, dtype=np.float32)
        norm = float(np.linalg.norm(feature))
        if (feature.ndim != 1 or len(feature) != self.dimension or
                not np.isfinite(feature).all() or not math.isfinite(norm) or norm <= 0):
            raise ValueError('Invalid upper query feature')
        feature = feature / norm
        return {int(i): float(feature @ self.vectors[int(i)]) for i in candidates}

    def query(self, image, source_sha256, central_box, detections, candidates):
        """One existing embedder call, after all-reference and actual query QA."""
        start = time.perf_counter()
        details = {'version': VERSION, 'accepted': False, 'model_calls': 0,
                   'gallery': self.assets, 'readiness': self.readiness(candidates),
                   'same_physical_view_correlated_evidence': True}
        if not details['readiness']['ready']:
            return dict(details, reason='not_all_compatible_references_ready', wall_ms=(time.perf_counter()-start)*1000)
        actual = inline_evidence({'source_sha256': source_sha256, 'decoded_size': list(image.size),
                                  'observed_central_box': native(central_box), 'detections': native(detections)})
        trace = dict(actual['canonical_json'], trace_path=actual['uri'], trace_sha256=actual['sha256'])
        quality = source_quality.query(image, source_sha256, native(central_box), trace)
        observation = inline_evidence(quality)
        geometry = source_quality.view_geometry(quality, observation['uri'], observation['sha256'])
        details.update(actual_detector_capture=actual, actual_quality_capture=observation,
                       query_geometry=geometry)
        if not geometry.get('accepted'):
            return dict(details, reason=geometry.get('reason'), wall_ms=(time.perf_counter()-start)*1000)
        crop = image.convert('RGB').crop(geometry['box'])
        details['model_calls'] = 1
        try:
            feature = self.embedder.features([crop])[0]
            scores = self.score(feature, candidates)
        except Exception as error:
            return dict(details, reason='upper_model_or_score_error',
                        errors=[{'type':type(error).__name__, 'message':str(error)}],
                        wall_ms=(time.perf_counter()-start)*1000)
        needed = list(map(int, candidates))
        return dict(details, accepted=True, reason='actual_upper_view_all_required_references_scored',
                    scores=scores, reference_proofs={i: self.proofs[i] for i in needed},
                    expected_identity={'catalog_sha256': self.assets['catalog_sha256'],
                                       'encoder_binding_sha256': self.binding_sha256,
                                       'gallery_manifest_sha256': self.assets['manifest_sha256'],
                                       'query_source_sha256': source_sha256,
                                       'reference_rows': {i: self.reference_rows[i] for i in needed}},
                    wall_ms=(time.perf_counter()-start)*1000)
