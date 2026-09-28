"""FP32 ONNX Runtime SO400M vision encoder, with the unchanged CPU target gate.

Only the SO image embedding implementation is swapped. Base224 wine gating,
RT-DETR, OWLv2-640 fallback, full index, and ranked-output code stay identical.
The exported graph has a fixed batch-one 384x384 input.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from fast_owl_pipeline import SO640Pipeline


class ORTEmbedder:
    def __init__(self, device: str, model_key: str):
        if device != 'cpu' or model_key != 'so400m384':
            raise ValueError('FP32 ONNX ablation is CPU SO400M only')
        from transformers import AutoProcessor
        import onnxruntime as ort

        directory = Path(os.environ['NIGHT_SO_ONNX_DIR'])
        if not (directory / 'vision.onnx').is_file():
            raise FileNotFoundError(directory / 'vision.onnx')
        self.processor = AutoProcessor.from_pretrained(directory / 'processor')
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.environ.get('NIGHT_SO_ONNX_THREADS', '4'))
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / 'vision.onnx'),
                                            sess_options=options,
                                            providers=['CPUExecutionProvider'])

    def features(self, images, batch_size=16):
        vectors = []
        for image in images:
            pixels = self.processor(images=image, return_tensors='np')['pixel_values']
            if pixels.shape != (1, 3, 384, 384) or pixels.dtype != np.float32:
                raise ValueError(f'unexpected processed pixels {pixels.shape} {pixels.dtype}')
            vectors.append(self.session.run(['embedding'], {'pixel_values': pixels})[0][0])
        return np.stack(vectors).astype(np.float32, copy=False)


class Pipeline(SO640Pipeline):
    def __init__(self, catalog_path, index_dir, device):
        import detector_encoder_server
        detector_encoder_server.Embedder = ORTEmbedder
        super().__init__(catalog_path, index_dir, device)
