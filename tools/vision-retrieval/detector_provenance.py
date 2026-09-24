"""Record reproducible, public-only detector experiment identity."""
import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from detector_variants import (
    GEOMETRIC_LABEL_MODE, YOLO26_WEIGHTS, YOLOE_BOTTLE_CLASSES,
    YOLOE_LABEL_CLASSES, YOLOE_WEIGHTS, RTDETR_ID, RTDETR_REV,
)
from model import OWL_ID, OWL_REV, SIGLIP_ID, SIGLIP_REV


def sha(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pod-id', required=True)
    parser.add_argument('--hourly-usd', type=float, required=True)
    args = parser.parse_args()
    import torch
    import transformers
    import ultralytics
    import paddleocr
    code_dir = Path(__file__).parent
    data = args.root/'data'
    source_names = (
        'model.py', 'server.py', 'detector_variants.py', 'detector_server.py',
        'detector_run.py', 'detector_export_eval.py', 'detector_provenance.py',
        'ranking.py', 'fuse.py', 'label_context_v2.py',
        'gray_label_ablation.py', 'gray_export_eval.py',
        'so400m_ablation.py', 'so400m_export_eval.py',
        'encoder_detector_composition.py', 'detector_cpu_benchmark.sh',
        'detector_encoder_server.py',
    )
    record = {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'pod_id': args.pod_id, 'hourly_usd': args.hourly_usd,
        'no_training': True, 'gold_on_inference_pod': False,
        'platform': platform.platform(), 'python': platform.python_version(),
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'packages': {
            'torch': torch.__version__, 'transformers': transformers.__version__,
            'ultralytics': ultralytics.__version__, 'paddleocr': paddleocr.__version__,
        },
        'weights': {
            YOLOE_WEIGHTS: sha(code_dir/YOLOE_WEIGHTS),
            YOLO26_WEIGHTS: sha(code_dir/YOLO26_WEIGHTS),
            'mobileclip2_b.ts': sha(code_dir/'mobileclip2_b.ts'),
            'owlv2': OWL_ID+'@'+OWL_REV,
            'siglip2': SIGLIP_ID+'@'+SIGLIP_REV,
            'rtdetr_r18vd': RTDETR_ID+'@'+RTDETR_REV,
            'siglip2_so400m_patch16_384': 'google/siglip2-so400m-patch16-384@dd658faac399427308559e2c3ac1e99cbe43845d',
        },
        'source_sha256': {name: sha(code_dir/name) for name in source_names},
        'inputs_sha256': {
            'frozen_public_suite': sha(data/'eval/baskets/v1.json'),
            'organizer_public_queries': sha(data/'organizer/queries-bundle.json'),
            'catalog_public': sha(data/'catalog/catalog-bundle.json'),
            'v2_index': sha(data/'index-v2/index.npz'),
            'v2_index_info': sha(data/'index-v2/index-info.json'),
            'reference_gated_index': sha(data/'index-reference-gated-v1/index.npz'),
            'reference_gate_decisions': sha(data/'index-reference-gated-v1/reference-decisions.json'),
        },
        'yoloe_bottle_classes': YOLOE_BOTTLE_CLASSES,
        'yoloe_label_classes': YOLOE_LABEL_CLASSES,
        'yolo26n_class': 'COCO bottle',
        'yolo26n_geometric_query_label_mode': GEOMETRIC_LABEL_MODE,
        'fixed_fusion_weights': {'whole': .25, 'label': .35, 'ocr': .40},
        'license_references': {
            'ultralytics_code_and_models': 'https://www.ultralytics.com/license',
            'yoloe_docs': 'https://docs.ultralytics.com/models/yoloe',
            'yolo26_docs': 'https://docs.ultralytics.com/models/yolo26',
            'clip_dependency': 'https://github.com/ultralytics/CLIP',
            'mobileclip2_dependency': 'https://github.com/apple/ml-mobileclip',
            'mobileclip2_model_license': 'https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS',
            'rtdetr_weights': 'https://huggingface.co/PekingU/rtdetr_r18vd',
            'rtdetr_code': 'https://github.com/lyuwenyu/RT-DETR/blob/main/LICENSE',
            'siglip2_so400m_weights': 'https://huggingface.co/google/siglip2-so400m-patch16-384',
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'file': str(args.out), 'gpu': record['gpu'],
                      'source_files': len(source_names)}))


if __name__ == '__main__':
    main()
