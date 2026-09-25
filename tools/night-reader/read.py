"""Gold-blind Qwen3-VL-2B target-label transcription."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import torch
from PIL import Image, ImageOps
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

MODEL = "Qwen/Qwen3-VL-2B-Instruct"
REVISION = "89644892e4d85e24eaac8bacfd4f463576704203"
MAX_EDGE = 768
MAX_NEW_TOKENS = 128
PROMPT = (
    "Задача OCR: выпиши только надписи, которые видны на этикетке, по строкам. "
    "Никаких вступлений, описаний, исправлений и догадок. "
    "Если ни одной надписи не читается, напиши ровно <EMPTY>."
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_image(path: Path):
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    original = image.size
    scale = min(1.0, MAX_EDGE / max(original))
    if scale < 1.0:
        image = image.resize((max(1, round(original[0] * scale)),
                              max(1, round(original[1] * scale))), Image.Resampling.LANCZOS)
    return image, original


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--crop-root", type=Path, required=True)
    p.add_argument("--sample-ids", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    rows = [json.loads(line) for line in args.inputs.read_text().splitlines() if line]
    selected = None
    if args.sample_ids:
        selected = set(json.loads(args.sample_ids.read_text())["case_ids"])
        rows = [r for r in rows if r["case_id"] in selected]
        if len(rows) != len(selected):
            raise ValueError("sample IDs missing from input manifest")
    if args.out.exists():
        existing = [json.loads(line) for line in args.out.read_text().splitlines() if line]
        done = {r["case_id"] for r in existing}
    else:
        done = set()
    if len(done) == len(rows):
        print(json.dumps({"complete": True, "rows": len(rows)}), flush=True)
        return
    load_start = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL, revision=REVISION, torch_dtype=torch.bfloat16,
        device_map="cuda:0", attn_implementation="sdpa").eval()
    torch.cuda.synchronize()
    print(json.dumps({"model_loaded": True, "load_s": round(time.perf_counter()-load_start, 3),
                      "model": MODEL, "revision": REVISION}), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as output:
        for i, row in enumerate(rows, 1):
            if row["case_id"] in done:
                continue
            result = {"case_id": row["case_id"], "track": row["track"],
                      "dataset": row["dataset"], "query_sha256": row["query_sha256"],
                      "model": MODEL, "revision": REVISION,
                      "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
                      "max_edge": MAX_EDGE, "max_new_tokens": MAX_NEW_TOKENS,
                      "status": "no_target", "text": "", "elapsed_ms": 0}
            if row["crop"]:
                crop = args.crop_root / Path(row["crop"]).name
                result["crop_sha256"] = sha(crop)
                start = time.perf_counter()
                try:
                    image, original = read_image(crop)
                    result["crop_size"] = list(original)
                    result["model_image_size"] = list(image.size)
                    messages = [{"role": "user", "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": PROMPT},
                    ]}]
                    inputs = processor.apply_chat_template(
                        messages, add_generation_prompt=True, tokenize=True,
                        return_dict=True, return_tensors="pt").to(model.device)
                    with torch.inference_mode():
                        generated = model.generate(**inputs, do_sample=False,
                                                   max_new_tokens=MAX_NEW_TOKENS,
                                                   use_cache=True)
                    torch.cuda.synchronize()
                    tail = generated[0, inputs["input_ids"].shape[-1]:]
                    result["text"] = processor.decode(tail, skip_special_tokens=True).strip()
                    result["generated_tokens"] = int(len(tail))
                    result["status"] = "ok"
                except Exception as exc:
                    result["status"] = "error"
                    result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
                result["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            if i % 10 == 0 or args.sample_ids:
                print(json.dumps({"processed": i, "total": len(rows),
                                  "case_id": row["case_id"], "status": result["status"],
                                  "elapsed_ms": result["elapsed_ms"]}), flush=True)
    print(json.dumps({"complete": True, "rows": len(rows)}), flush=True)


if __name__ == "__main__":
    main()
