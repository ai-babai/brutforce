from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


OPAQUE_CLASS_RE = re.compile(r"^class_\d+$", re.IGNORECASE)
BOUNDARY_EPSILON = 0.00001


def parse_yolo_label(path: Path, width: int, height: int, media_id: str) -> tuple[list[dict[str, object]], list[str]]:
    boxes: list[dict[str, object]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"line {line_number}: expected 5 fields, got {len(parts)}")
            continue
        try:
            class_id = int(parts[0])
            x_center, y_center, box_width, box_height = map(float, parts[1:])
        except ValueError as exc:
            errors.append(f"line {line_number}: {exc}")
            continue
        x_min = x_center - box_width / 2
        y_min = y_center - box_height / 2
        x_max = x_center + box_width / 2
        y_max = y_center + box_height / 2
        structurally_valid = (
            class_id >= 0
            and box_width > 0
            and box_height > 0
        )
        within_rounding_tolerance = (
            -BOUNDARY_EPSILON <= x_min <= x_max <= 1 + BOUNDARY_EPSILON
            and -BOUNDARY_EPSILON <= y_min <= y_max <= 1 + BOUNDARY_EPSILON
        )
        valid = structurally_valid and within_rounding_tolerance
        clipped = valid and not (0 <= x_min <= x_max <= 1 and 0 <= y_min <= y_max <= 1)
        clean_x_min = min(1.0, max(0.0, x_min))
        clean_y_min = min(1.0, max(0.0, y_min))
        clean_x_max = min(1.0, max(0.0, x_max))
        clean_y_max = min(1.0, max(0.0, y_max))
        if not valid:
            errors.append(f"line {line_number}: invalid normalized box")
        boxes.append(
            {
                "bbox_id": stable_id("bbox_retail", f"{media_id}:{line_number}"),
                "media_id": media_id,
                "source_label_path": path.name,
                "source_line": line_number,
                "class_id": class_id,
                "class_name": "alcohol_product",
                "format": "yolo_cxcywh_normalized",
                "x_center": x_center,
                "y_center": y_center,
                "width": box_width,
                "height": box_height,
                "x_min_px": round(clean_x_min * width, 3),
                "y_min_px": round(clean_y_min * height, 3),
                "x_max_px": round(clean_x_max * width, 3),
                "y_max_px": round(clean_y_max * height, 3),
                "validation_status": "clipped_rounding" if clipped else ("valid" if valid else "invalid"),
            }
        )
    return boxes, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Retail Alcohol Detection classification and YOLO labels.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    dataset_root = project_root / "Dataset"
    dataset_dir = dataset_root / "05_retail_alcohol_detection"
    extraction_root = dataset_dir / "media" / "source_extract" / "datasets"
    classification_root = extraction_root / "classification"
    detection_image_root = extraction_root / "detection" / "images"
    detection_label_root = extraction_root / "detection" / "labels"
    tables_dir = dataset_dir / "tables"
    for required in (classification_root, detection_image_root, detection_label_root):
        if not required.is_dir():
            raise FileNotFoundError(required)

    media_records: list[dict[str, object]] = []
    bbox_records: list[dict[str, object]] = []
    validation_errors: list[dict[str, object]] = []
    hash_to_media: dict[str, list[str]] = defaultdict(list)

    classification_images = sorted(classification_root.rglob("*.jpg"))
    for index, path in enumerate(classification_images, start=1):
        relative = relative_posix(path, dataset_root)
        media_id = stable_id("media_retail", relative)
        class_name = path.parent.name
        dataset_partition = path.parent.parent.name
        digest = sha256_file(path)
        probe = image_probe(path, calculate_dhash=True)
        opaque = bool(OPAQUE_CLASS_RE.fullmatch(class_name))
        record = {
            "manifest_version": "1.0.0",
            "source_id": "retail-alcohol-detection-kaggle",
            "media_id": media_id,
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "task": "classification",
            "dataset_partition": dataset_partition,
            "class_id": class_name,
            "class_name": None if opaque else class_name,
            "label_status": "provided_opaque_class" if opaque else "provided_named_class",
            "bbox_status": "not_applicable_cropped_classification_image",
            "training_candidate": probe["decode_status"] == "ok",
            **probe,
        }
        media_records.append(record)
        hash_to_media[digest].append(media_id)
        if index % 250 == 0:
            print(f"Audited classification image {index}/{len(classification_images)}", flush=True)

    detection_images = sorted(detection_image_root.glob("*.jpg"))
    detection_stems = {path.stem for path in detection_images}
    label_files = sorted(detection_label_root.glob("*.txt"))
    label_stems = {path.stem for path in label_files}
    missing_labels = sorted(detection_stems - label_stems)
    orphan_labels = sorted(label_stems - detection_stems)

    for index, path in enumerate(detection_images, start=1):
        relative = relative_posix(path, dataset_root)
        media_id = stable_id("media_retail", relative)
        digest = sha256_file(path)
        probe = image_probe(path, calculate_dhash=True)
        label_path = detection_label_root / f"{path.stem}.txt"
        boxes: list[dict[str, object]] = []
        errors: list[str] = []
        if label_path.is_file() and probe["decode_status"] == "ok":
            boxes, errors = parse_yolo_label(label_path, int(probe["width"]), int(probe["height"]), media_id)
            bbox_records.extend(boxes)
        elif not label_path.is_file():
            errors.append("missing label file")
        else:
            errors.append("image decode failed; bbox pixel conversion unavailable")
        if errors:
            validation_errors.append({"media_id": media_id, "relative_path": relative, "errors": errors})
        valid_boxes = sum(box["validation_status"] in {"valid", "clipped_rounding"} for box in boxes)
        record = {
            "manifest_version": "1.0.0",
            "source_id": "retail-alcohol-detection-kaggle",
            "media_id": media_id,
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "task": "detection",
            "class_id": 0,
            "class_name": "alcohol_product",
            "label_status": "provided_bbox_label" if valid_boxes else "invalid_or_missing_bbox_label",
            "bbox_status": "valid" if valid_boxes and not errors else "invalid",
            "bbox_count": len(boxes),
            "valid_bbox_count": valid_boxes,
            "training_candidate": probe["decode_status"] == "ok" and valid_boxes > 0 and not errors,
            **probe,
        }
        media_records.append(record)
        hash_to_media[digest].append(media_id)
        if index % 100 == 0:
            print(f"Audited detection image {index}/{len(detection_images)}", flush=True)

    for record in media_records:
        duplicate_ids = hash_to_media[str(record["sha256"])]
        record["exact_duplicate_group_id"] = (
            stable_id("exact", str(record["sha256"])) if len(duplicate_ids) > 1 else None
        )

    counts = {
        "media": write_jsonl(tables_dir / "media.jsonl", media_records),
        "bboxes": write_jsonl(tables_dir / "bboxes.jsonl", bbox_records),
        "validation_errors": write_jsonl(tables_dir / "validation_errors.jsonl", validation_errors),
    }
    summary = {
        "manifest_version": "1.0.0",
        "source_id": "retail-alcohol-detection-kaggle",
        "counts": {
            **counts,
            "classification_images": len(classification_images),
            "classification_named": sum(record["label_status"] == "provided_named_class" for record in media_records),
            "classification_opaque": sum(record["label_status"] == "provided_opaque_class" for record in media_records),
            "detection_images": len(detection_images),
            "detection_label_files": len(label_files),
            "valid_bboxes": sum(box["validation_status"] in {"valid", "clipped_rounding"} for box in bbox_records),
            "clipped_rounding_bboxes": sum(box["validation_status"] == "clipped_rounding" for box in bbox_records),
            "invalid_bboxes": sum(box["validation_status"] == "invalid" for box in bbox_records),
            "images_decode_error": sum(record["decode_status"] != "ok" for record in media_records),
            "missing_label_files": len(missing_labels),
            "orphan_label_files": len(orphan_labels),
            "exact_duplicate_groups": sum(len(ids) > 1 for ids in hash_to_media.values()),
        },
        "distributions": {
            "classification_named_classes": Counter(
                str(record["class_name"])
                for record in media_records
                if record["task"] == "classification" and record["class_name"]
            ),
            "bbox_class_ids": Counter(str(box["class_id"]) for box in bbox_records),
        },
        "gates": {
            "all_images_have_label_or_bbox_status": all(record["label_status"] for record in media_records),
            "all_detection_images_have_label_file": not missing_labels,
            "all_detection_labels_have_image": not orphan_labels,
            "all_bboxes_usable": not any(box["validation_status"] == "invalid" for box in bbox_records),
            "exact_russian_wine_labels_available": False,
        },
        "missing_label_stems": missing_labels,
        "orphan_label_stems": orphan_labels,
    }
    write_json(tables_dir / "SUMMARY.json", summary)
    print(f"PASS: audited {len(media_records)} images and {len(bbox_records)} bboxes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
