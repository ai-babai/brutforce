#!/usr/bin/env python3
"""Render deterministic bbox overlays for human semantic spot-checking."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Dataset"
OUT = ROOT / "tmp/bbox-audit"
FONT = ImageFont.load_default()


def load(path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines() if line.strip()]


def media_path(value: str) -> Path:
    path = Path(value)
    return (ROOT / path) if path.parts and path.parts[0].casefold() == "dataset" else (DATASET / path)


def fit(image: Image.Image, size: tuple[int, int]) -> tuple[Image.Image, float, int, int]:
    image = image.convert("RGB")
    scale = min(size[0] / image.width, size[1] / image.height)
    width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    resized = image.resize((width, height), Image.Resampling.LANCZOS)
    return resized, scale, (size[0] - width) // 2, (size[1] - height) // 2


def contact_sheet(items: list[tuple[Path, list[tuple[float, float, float, float, str]]]], destination: Path, columns: int = 4) -> None:
    cell_w, cell_h = 360, 360
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (path, boxes) in enumerate(items):
        with Image.open(path) as source:
            image, scale, ox, oy = fit(source, (cell_w, cell_h - 24))
        x0 = (index % columns) * cell_w
        y0 = (index // columns) * cell_h
        canvas.paste(image, (x0 + ox, y0 + oy + 24))
        draw.text((x0 + 4, y0 + 4), path.name[:48], fill="black", font=FONT)
        for bx1, by1, bx2, by2, label in boxes:
            coords = (x0 + ox + bx1 * scale, y0 + 24 + oy + by1 * scale, x0 + ox + bx2 * scale, y0 + 24 + oy + by2 * scale)
            draw.rectangle(coords, outline="#ff2020", width=2)
            draw.text((coords[0] + 2, max(y0 + 24, coords[1] + 2)), label[:24], fill="#ff2020", font=FONT, stroke_width=1, stroke_fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, quality=92)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    retail_media = [row for row in load("Dataset/05_retail_alcohol_detection/tables/media.jsonl") if row.get("task") == "detection"]
    retail_boxes = defaultdict(list)
    for row in load("Dataset/05_retail_alcohol_detection/tables/bboxes.jsonl"):
        retail_boxes[row["media_id"]].append((row["x_min_px"], row["y_min_px"], row["x_max_px"], row["y_max_px"], row["class_name"]))
    sample_indexes = [round(index * (len(retail_media) - 1) / 11) for index in range(12)]
    retail_items = [(media_path(retail_media[index]["relative_path"]), retail_boxes[retail_media[index]["media_id"]]) for index in sample_indexes]
    contact_sheet(retail_items, OUT / "retail-bbox-sample.jpg")

    rf_media = {row["media_id"]: row for row in load("Dataset/09_rf100_wine_labels/tables/media.jsonl")}
    rf_boxes = defaultdict(list)
    boxes_in_order = []
    for row in load("Dataset/09_rf100_wine_labels/tables/bboxes.jsonl"):
        x, y, w, h = row["bbox_xywh_pixels"]
        rf_boxes[row["media_id"]].append((x, y, x + w, y + h, row["category_name"]))
        boxes_in_order.append((int(row["category_id"]), row["media_id"]))
    representative = {}
    used_media = set()
    for category_id, media_id in boxes_in_order:
        if category_id not in representative and media_id not in used_media:
            representative[category_id] = media_id
            used_media.add(media_id)
    rf_items = []
    for category_id, media_id in sorted(representative.items()):
        row = rf_media[media_id]
        rf_items.append((media_path(row["path"]), rf_boxes[media_id]))
    contact_sheet(rf_items, OUT / "rf100-bbox-sample.jpg")

    result = {
        "retail_sample_images": len(retail_items),
        "retail_sampling": "12 deterministic positions across sorted detection manifest",
        "rf100_sample_images": len(rf_items),
        "rf100_sampling": "one diverse representative for every category ID present in bbox annotations (12 of 13 declared categories)",
        "overlays": [
            (OUT / "retail-bbox-sample.jpg").relative_to(ROOT).as_posix(),
            (OUT / "rf100-bbox-sample.jpg").relative_to(ROOT).as_posix(),
        ],
    }
    (OUT / "render-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
