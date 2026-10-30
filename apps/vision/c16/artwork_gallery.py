"""Startup-only cached reference artwork bindings; query pixels only at runtime."""
import json
import math
import time
from pathlib import Path
import numpy as np
from chromatic_artwork import descriptor, VERSION as DESCRIPTOR_VERSION
from artwork_pairwise import histogram
from upper_gallery import sha

VERSION='source-bound-upper-artwork-cache-v1'


class ArtworkGallery:
    def __init__(self,folder,upper_gallery,*,expected_manifest_sha256,expected_features_sha256):
        folder=Path(folder);manifest=folder/'assets/upper-artwork.json';features=folder/'assets/upper-artwork.npz'
        if sha(manifest)!=expected_manifest_sha256 or sha(features)!=expected_features_sha256:
            raise ValueError('Frozen artwork descriptor archive mismatch')
        m=json.loads(manifest.read_text());assets=upper_gallery.assets
        if (m.get('version')!=VERSION or m.get('descriptor_version')!=DESCRIPTOR_VERSION or
                m.get('features_sha256')!=expected_features_sha256 or
                m.get('upper_gallery_manifest_sha256')!=assets['manifest_sha256'] or
                m.get('upper_gallery_features_sha256')!=assets['features_sha256'] or
                m.get('catalog_sha256')!=assets['catalog_sha256'] or
                m.get('encoder_binding_sha256')!=assets['encoder_binding_sha256'] or
                not m.get('acquisition_source_freeze_sha256')):
            raise ValueError('Cached descriptor/upper/source/encoder binding mismatch')
        with np.load(features,allow_pickle=False) as data:
            if set(data.files)!={'histograms','catalog_indices'}:raise ValueError('Unknown artwork archive closure')
            h=data['histograms'];ids=data['catalog_indices']
        if h.dtype!=np.float64 or ids.dtype!=np.int64 or h.shape!=(len(ids),24) or not np.isfinite(h).all():
            raise ValueError('Invalid cached artwork archive')
        if len(ids)!=len(set(map(int,ids))) or len(ids)!=len(m['records']) or set(map(int,ids))!=set(upper_gallery.proofs):
            raise ValueError('Cached descriptor rows do not account for every upper feature')
        self.descriptors={};self.unready={};self.upper_gallery=upper_gallery
        for offset,row in enumerate(m['records']):
            i=int(ids[offset]);p=upper_gallery.proofs[i]
            if (row.get('catalog_index')!=i or row.get('vector_row')!=offset or
                    any(row.get(k)!=p.get(k) for k in ('slug','reference_sha256','view_crop_sha256'))):
                raise ValueError('Reference descriptor vector/source/crop row mismatch')
            d=dict(row['descriptor'],histogram=h[offset].tolist())
            if d.get('accepted') is True:
                if d.get('crop_RGB_sha256')!=p['view_crop_sha256']:raise ValueError('Descriptor actual crop SHA mismatch')
                histogram(d,'reference');self.descriptors[i]=d
            else:self.unready[i]=row
        self.assets={'version':VERSION,'manifest_sha256':expected_manifest_sha256,
                     'features_sha256':expected_features_sha256,'descriptor_version':DESCRIPTOR_VERSION,
                     'upper_gallery_manifest_sha256':assets['manifest_sha256'],
                     'encoder_binding_sha256':assets['encoder_binding_sha256'],
                     'catalog_sha256':assets['catalog_sha256'],'reference_count':len(m['records']),
                     'ready_count':len(self.descriptors),'unready_count':len(self.unready)}

    def ready(self,candidates):
        return self.upper_gallery.ready(candidates) and all(int(i) in self.descriptors for i in candidates)

    def references(self,candidates):
        if not self.ready(candidates):raise ValueError('Missing artwork competitor cannot be skipped')
        return {int(i):self.descriptors[int(i)] for i in candidates}

    def query(self,image,geometry):
        start=time.perf_counter()
        if geometry.get('accepted') is not True:raise ValueError('Actual query upper geometry required')
        d=descriptor(image.convert('RGB').crop(geometry['box']),role='query')
        if d['crop_RGB_sha256']!=geometry.get('upper_rgb_crop_sha256'):
            raise ValueError('Actual query descriptor differs from upper encoder crop')
        return dict(d,wall_ms=(time.perf_counter()-start)*1000)
