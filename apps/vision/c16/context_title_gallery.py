"""Startup-bound distinct context-title assets; no model loading or inference."""
import hashlib,json,math
from pathlib import Path
import numpy as np
from candidate_policy import canonical_norm
from title_reacquisition import title_context,grape_relation
from title_gallery import TitleGallery

VERSION='context-title-row-gallery-v1-existingBatch32'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

class ContextTitleGallery:
    def __init__(self,folder,catalog_path,metadata_path,references,engine,verified_title_gallery=None):
        folder=Path(folder);self.manifest_path=folder/'assets/context-title-gallery.json';self.features_path=folder/'assets/context-title-gallery.npz'
        m=json.loads(self.manifest_path.read_text());self.manifest=m
        if m.get('gallery_version')!=VERSION:raise ValueError('Wrong context gallery version')
        if m['catalog_sha256']!=sha(catalog_path) or m['attributes_sha256']!=sha(metadata_path):raise ValueError('Context catalogue/attributes mismatch')
        if m['features_sha256']!=sha(self.features_path):raise ValueError('Context feature digest mismatch')
        if not m.get('source_plan_sha256') or not m.get('geometry_freeze_sha256') or not m.get('model_receipt_sha256'):raise ValueError('Missing context acquisition/encoder lineage')
        if verified_title_gallery is None:
            # Same existing encoder; at most one verification pass at startup.
            TitleGallery.verify_encoder(self,engine,m['encoder_binding'])
        else:
            old=verified_title_gallery.assets
            if not old.get('encoder_binding_verified'):raise ValueError('Old encoder not already verified')
            for field in ('logical_files','batch_shape','dtype','crop_transform'):
                if old['encoder'].get(field)!=m['encoder_binding'].get(field):raise ValueError('Context encoder differs from verified C14 encoder')
            if engine.model.so_embedder.session.get_providers()!=['CPUExecutionProvider']:raise ValueError('Context encoder not CPU')
        self.assets={'encoder_binding_verified':True,'gallery_version':VERSION,
                     'manifest_sha256':sha(self.manifest_path),'features_sha256':sha(self.features_path),
                     'encoder':m['encoder_binding'],'source_plan_sha256':m['source_plan_sha256'],
                     'source_gallery_freeze_sha256':m['geometry_freeze_sha256']}
        attrs=json.loads(Path(metadata_path).read_text())['rows']
        if [r['slug'] for r in attrs]!=[r['slug'] for r in references[:len(attrs)]]:raise ValueError('Context attribute order mismatch')
        vocabulary=set().union(*(set(r['grape']) for r in attrs))
        with np.load(self.features_path,allow_pickle=False) as archive:
            matrix=np.asarray(archive['features'],dtype=np.float32);ids=[str(x) for x in archive['ids']]
        if matrix.ndim!=2 or len(ids)!=len(matrix) or len(set(ids))!=len(ids) or not np.isfinite(matrix).all():raise ValueError('Invalid context feature matrix')
        norms=np.linalg.norm(matrix,axis=1)
        if not np.isfinite(norms).all() or np.any(norms<=0):raise ValueError('Invalid context feature norms')
        indices=[]
        for identifier in ids:
            if not identifier.startswith('catalog:') or not identifier[8:].isdigit():raise ValueError('Non-catalogue context vector')
            i=int(identifier[8:])
            if not 0<=i<len(references):raise ValueError('Context catalogue index out of range')
            indices.append(i)
        if len(set(indices))!=len(indices):raise ValueError('Duplicate numeric context vector index')
        self.vectors={i:v/n for i,v,n in zip(indices,matrix,norms)}
        feature_rows={}
        for row in m['feature_rows']:
            i=int(row['catalog_index'])
            if i in feature_rows:raise ValueError('Duplicate context feature row')
            feature_rows[i]=row
        if set(feature_rows)!=set(self.vectors):raise ValueError('Context feature identity closure mismatch')
        planned=list(map(int,m['planned_catalog_indices']))
        if len(set(planned))!=len(planned):raise ValueError('Duplicate planned context record')
        self.proofs={}
        for record in m['reference_records']:
            i=int(record['index'])
            if i in self.proofs or not 0<=i<len(references):raise ValueError('Invalid/duplicate context record')
            if record['slug']!=references[i]['slug'] or record['reference_sha256']!=references[i]['sha256']:raise ValueError('Context reference catalogue binding mismatch')
            proof=dict(record.get('acquisition') or {})
            proof.update(source_sha256=record['reference_sha256'],catalog_index=i,
                         catalog_slug=record['slug'],catalog_sha256=m['catalog_sha256'])
            if proof.get('accepted') is True:
                row=feature_rows.get(i)
                if row is None or row['sha256']!=references[i]['sha256'] or row['box']!=proof.get('box') or row.get('angle_degrees',0)!=proof.get('angle_degrees',0):raise ValueError('Context crop/vector/proof mismatch')
                if row.get('fillcolor',[255,255,255])!=[255,255,255]:raise ValueError('Context rotation fill mismatch')
                if proof.get('role')!='following_product_title_row' or proof.get('proof_contract')!='reference_catalog_identity_raw_OCR_location' or not proof.get('anchor') or not proof.get('following_row'):raise ValueError('Missing complete physical context role')
                metadata=set(attrs[i]['grape']) if i<len(attrs) else set()
                context=title_context(references[i].get('title',''),metadata,vocabulary,canonical_norm)
                if not context['context'] or record.get('context')!=context['context']:raise ValueError('Context title/metadata identity mismatch')
                location=set(proof.get('catalog_grapes',()))
                if grape_relation(location,metadata) not in ('exact','specificity_uncertainty') or location!={context['anchor_literal']}:raise ValueError('Wrong reference whole location anchor')
                proof['catalog_metadata_grapes']=sorted(metadata)
                proof['catalog_title_context']=context['context']
            elif i in self.vectors:raise ValueError('Context vector lacks accepted physical proof')
            self.proofs[i]=proof
        if set(self.proofs)!=set(planned):raise ValueError('Missing/unaccounted planned context references')
        if any(not self.proofs.get(i,{}).get('accepted') for i in self.vectors):raise ValueError('Context feature lacks reference proof')
        if verified_title_gallery is not None and verified_title_gallery.vectors:
            if matrix.shape[1]!=len(next(iter(verified_title_gallery.vectors.values()))):raise ValueError('Context/old encoder feature dimension mismatch')

    def ready(self,candidates):
        indices=list(map(int,candidates));hashes=[]
        if not indices or len(set(indices))!=len(indices):return False
        for i in indices:
            proof=self.proofs.get(i,{})
            if i not in self.vectors or proof.get('accepted') is not True or proof.get('errors') or proof.get('budget',{}).get('exhausted'):return False
            hashes.append(proof.get('source_sha256'))
        return None not in hashes and len(set(hashes))==len(hashes)

    def score(self,feature,candidates):
        candidates=list(map(int,candidates))
        if not self.ready(candidates):raise ValueError('All required context references must be ready and unique')
        feature=np.asarray(feature,dtype=np.float32);norm=float(np.linalg.norm(feature))
        if feature.ndim!=1 or not np.isfinite(feature).all() or not math.isfinite(norm) or norm<=0:raise ValueError('Invalid context query feature')
        if any(len(self.vectors[i])!=len(feature) for i in candidates):raise ValueError('Context feature dimension mismatch')
        feature=feature/norm
        return {i:float(feature@self.vectors[i]) for i in candidates}
