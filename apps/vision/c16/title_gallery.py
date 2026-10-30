"""Immutable existing-model derived gallery, not a replacement retrieval index."""
import hashlib,json,math,os
from pathlib import Path
import numpy as np
VERSION='catalog-title-row-gallery-v1-existingBatch32'
def sha(p):
    with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
class TitleGallery:
    def __init__(self,folder,catalog_path,metadata_path,references,engine):
        folder=Path(folder);self.manifest_path=folder/'assets/title-gallery.json';self.features_path=folder/'assets/title-gallery.npz'
        self.manifest=json.loads(self.manifest_path.read_text());m=self.manifest
        if m['catalog_sha256']!=sha(catalog_path) or m['attributes_sha256']!=sha(metadata_path):raise ValueError('Title gallery/catalog asset mismatch')
        if m['features_sha256']!=sha(self.features_path):raise ValueError('Title gallery feature digest mismatch')
        self.verify_encoder(engine,m['encoder_binding'])
        self.assets={'encoder_binding_verified':True,'manifest_sha256':sha(self.manifest_path),'features_sha256':sha(self.features_path),'gallery_version':VERSION,'encoder':m['encoder_binding'],'source_gallery_freeze_sha256':m['geometry_freeze_sha256']}
        data=np.load(self.features_path,allow_pickle=False);matrix=np.asarray(data['features'],dtype=np.float32);ids=[str(x) for x in data['ids']]
        if matrix.ndim!=2 or len(ids)!=len(matrix) or len(ids)!=len(set(ids)) or not np.isfinite(matrix).all():raise ValueError('Invalid title feature matrix')
        norms=np.linalg.norm(matrix,axis=1)
        if not np.isfinite(norms).all() or np.any(norms<=0):raise ValueError('Invalid title feature norms')
        self.vectors={int(id.split(':')[1]):v/n for id,v,n in zip(ids,matrix,norms) if id.startswith('catalog:')}
        if len(self.vectors)!=len(ids):raise ValueError('Title gallery contains non-catalogue features')
        self.proofs={}; feature_rows={int(r['catalog_index']):r for r in m['feature_rows']}
        if set(feature_rows)!=set(self.vectors):raise ValueError('Feature row identity mismatch')
        for record in m['reference_records']:
            i=int(record['index']);proof=dict(record.get('acquisition') or {})
            proof['source_sha256']=record.get('reference_sha256');proof['catalog_index']=i;proof['catalog_title_context']=record.get('context','');proof['catalog_sha256']=m['catalog_sha256'];proof['catalog_slug']=record.get('slug')
            if proof.get('accepted'):
                row=feature_rows.get(i)
                if row is None or row['sha256']!=references[i].get('sha256') or record.get('slug')!=references[i].get('slug') or row['box']!=proof.get('box') or row.get('angle_degrees',0)!=proof.get('angle_degrees',0):raise ValueError('Geometry/feature/catalog binding mismatch')
            self.proofs[i]=proof
        if any(i not in self.proofs or not self.proofs[i].get('accepted') for i in self.vectors):raise ValueError('Feature lacks geometry-certified reference')
    def verify_encoder(self,engine,binding):
        """Cheap once at startup; no second model and no per-request scans."""
        directory=Path(os.environ['NIGHT_SO_ONNX_DIR']).resolve();model=engine.model.so_embedder
        actual_model=getattr(model.session,'_model_path',None)
        if actual_model is None or Path(actual_model).resolve()!=directory/'vision.onnx':raise ValueError('Loaded encoder path differs from verified assets')
        expected=binding['logical_files']
        actual_files={'vision.onnx','vision.onnx.data'}|{str(p.relative_to(directory)) for p in (directory/'processor').rglob('*') if p.is_file()}
        if actual_files!=set(expected):raise ValueError('Encoder graph/processor file closure mismatch')
        for name,digest in expected.items():
            if sha(directory/name)!=digest:raise ValueError('Existing encoder/processor digest mismatch: '+name)
        if model.session.get_providers()!=['CPUExecutionProvider']:raise ValueError('Title encoder is not existing CPU-only model')
        inputs=model.session.get_inputs()
        if len(inputs)!=1 or list(inputs[0].shape)!=binding['batch_shape'] or inputs[0].type!='tensor(float)' or binding['dtype']!='float32':raise ValueError('Title encoder tensor contract mismatch')
        configuration=json.loads((directory/'processor/preprocessor_config.json').read_text());processor=model.processor.image_processor
        for name in ('do_convert_rgb','do_normalize','do_rescale','do_resize','image_mean','image_std','resample','rescale_factor','size'):
            if getattr(processor,name,None)!=configuration.get(name):raise ValueError('Loaded image processor configuration mismatch: '+name)

    def ready(self,candidates):
        candidates=list(map(int,candidates));hashes=[]
        if not candidates:return False
        for i in candidates:
            proof=self.proofs.get(i,{})
            if i not in self.vectors or not proof.get('accepted') or proof.get('role')!='following_product_title_row' or proof.get('proof_contract')!='reference_catalog_identity_raw_OCR_location':return False
            hashes.append(proof.get('source_sha256'))
        return None not in hashes and len(set(hashes))==len(hashes)
    def score(self,feature,candidates):
        feature=np.asarray(feature,dtype=np.float32);norm=float(np.linalg.norm(feature))
        if feature.ndim!=1 or not np.isfinite(feature).all() or not math.isfinite(norm) or norm<=0:raise ValueError('Invalid query title feature')
        feature=feature/norm
        return {int(i):float(feature@self.vectors[int(i)]) for i in candidates}
