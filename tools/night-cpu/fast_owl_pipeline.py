"""Separate quality ablation: resize OWLv2 rescue to 640 pixels."""
import time
import types

from PIL import Image

from base224_pipeline import Pipeline as BasePipeline
from whole_encoder_server import Pipeline as SOPipeline
from model import clamp_box, iou


def resized_detect(self, image, prompts, threshold):
    start = time.perf_counter()
    detector_image = image.copy()
    detector_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    sx, sy = image.width / detector_image.width, image.height / detector_image.height
    inp = self.detector_processor(text=[prompts], images=detector_image,
                                  return_tensors='pt').to(self.device)
    with self.torch.inference_mode():
        out = self.detector(**inp, interpolate_pos_encoding=True)
    self._sync()
    res = self.detector_processor.post_process_object_detection(
        out, target_sizes=self.torch.tensor([detector_image.size[::-1]]),
        threshold=threshold)[0]
    raw = []
    for box, score, label in zip(res['boxes'], res['scores'], res['labels']):
        coords = box.tolist()
        b = clamp_box([coords[0]*sx, coords[1]*sy, coords[2]*sx, coords[3]*sy], image.size)
        raw.append({'box': b, 'score': float(score), 'prompt': prompts[int(label)]})
    raw.sort(key=lambda x: x['score'], reverse=True)
    distinct = []
    for item in raw:
        if all(iou(item['box'], prior['box']) < .65 for prior in distinct):
            distinct.append(item)
    return distinct[:12], round((time.perf_counter()-start)*1000)


def configure(model):
    model.detector_processor.image_processor.size = {'height': 640, 'width': 640}
    model._detect_prompts = types.MethodType(resized_detect, model)


class Base640Pipeline(BasePipeline):
    def __init__(self, catalog_path, index_dir, device):
        super().__init__(catalog_path, index_dir, device)
        configure(self.model)


class SO640Pipeline(SOPipeline):
    def __init__(self, catalog_path, index_dir, device):
        super().__init__(catalog_path, index_dir, device)
        configure(self.model)


Pipeline = SO640Pipeline
