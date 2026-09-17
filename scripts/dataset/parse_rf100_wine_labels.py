#!/usr/bin/env python3
"""Validate the RF100 Wine Labels COCO annotations and all images."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Dataset/09_rf100_wine_labels/media/source_extract"
TABLES = ROOT / "Dataset/09_rf100_wine_labels/tables"
SPLITS = ("train", "valid", "test")


def main() -> int:
    media_rows = []
    bbox_rows = []
    errors = []
    categories_by_id: dict[int, str] = {}
    expected_files: set[Path] = set()
    annotations_per_image = Counter()

    for split in SPLITS:
        split_dir = SOURCE / split
        annotation_path = split_dir / "_annotations.coco.json"
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        categories = {int(row["id"]): row["name"] for row in payload["categories"]}
        if categories_by_id and categories != categories_by_id:
            errors.append({"type": "category_mismatch", "split": split})
        categories_by_id = categories
        images = {int(row["id"]): row for row in payload["images"]}
        annotations = defaultdict(list)
        for annotation in payload["annotations"]:
            annotations[int(annotation["image_id"])].append(annotation)

        for coco_image_id, image in sorted(images.items()):
            path = split_dir / image["file_name"]
            expected_files.add(path.resolve())
            media_id = stable_id("media_rf100", f"{split}/{image['file_name']}")
            probe = image_probe(path, calculate_dhash=True) if path.exists() else {
                "decode_status": "missing", "image_format": None, "width": None,
                "height": None, "mode": None, "dhash64": None,
                "decode_error": "file missing",
            }
            sha = sha256_file(path) if path.exists() else None
            dimension_match = (
                probe["decode_status"] == "ok"
                and int(probe["width"]) == int(image["width"])
                and int(probe["height"]) == int(image["height"])
            )
            if not path.exists():
                errors.append({"type": "missing_image", "split": split, "file_name": image["file_name"]})
            elif probe["decode_status"] != "ok":
                errors.append({"type": "decode_error", "split": split, "file_name": image["file_name"], "error": probe["decode_error"]})
            elif not dimension_match:
                errors.append({"type": "dimension_mismatch", "split": split, "file_name": image["file_name"]})

            image_annotations = annotations.get(coco_image_id, [])
            media_rows.append({
                "media_id": media_id,
                "source_id": "rf100-wine-labels",
                "source_split": split,
                "source_coco_image_id": coco_image_id,
                "path": relative_posix(path, ROOT / "Dataset") if path.exists() else None,
                "file_name": image["file_name"],
                "sha256": sha,
                **probe,
                "annotation_status": "has_element_bboxes" if image_annotations else "no_bboxes",
                "bbox_count": len(image_annotations),
                "dimensions_match_coco": dimension_match,
                "sku_label_status": "unlabeled",
                "russian_wine_status": "unknown_not_derivable_from_coco",
            })

            width = float(image["width"])
            height = float(image["height"])
            for annotation in image_annotations:
                annotation_id = int(annotation["id"])
                category_id = int(annotation["category_id"])
                bbox = [float(value) for value in annotation["bbox"]]
                x, y, w, h = bbox
                valid = (
                    category_id in categories
                    and w > 0 and h > 0
                    and x >= -1e-6 and y >= -1e-6
                    and x + w <= width + 1e-6
                    and y + h <= height + 1e-6
                )
                if not valid:
                    errors.append({
                        "type": "invalid_bbox", "split": split,
                        "annotation_id": annotation_id, "image_id": coco_image_id,
                        "category_id": category_id, "bbox": bbox,
                    })
                annotations_per_image[media_id] += 1
                bbox_rows.append({
                    "bbox_id": stable_id("bbox_rf100", f"{split}/{annotation_id}"),
                    "media_id": media_id,
                    "source_split": split,
                    "source_annotation_id": annotation_id,
                    "category_id": category_id,
                    "category_name": categories.get(category_id),
                    "bbox_xywh_pixels": bbox,
                    "bbox_xyxy_normalized": [x / width, y / height, (x + w) / width, (y + h) / height],
                    "validation_status": "valid" if valid else "invalid",
                    "iscrowd": int(annotation.get("iscrowd", 0)),
                })

    actual_images = {
        path.resolve()
        for split in SPLITS
        for path in (SOURCE / split).glob("*.jpg")
    }
    for orphan in sorted(actual_images - expected_files):
        errors.append({"type": "orphan_image", "path": relative_posix(orphan, ROOT / "Dataset")})

    sha_groups = defaultdict(list)
    dhash_groups = defaultdict(list)
    for row in media_rows:
        if row["sha256"]:
            sha_groups[row["sha256"]].append(row)
        if row["dhash64"]:
            dhash_groups[row["dhash64"]].append(row)
    exact_duplicate_groups = [rows for rows in sha_groups.values() if len(rows) > 1]
    exact_cross_split_groups = [
        rows for rows in exact_duplicate_groups
        if len({row["source_split"] for row in rows}) > 1
    ]
    dhash_cross_split_groups = [
        rows for rows in dhash_groups.values()
        if len(rows) > 1 and len({row["source_split"] for row in rows}) > 1
    ]

    TABLES.mkdir(parents=True, exist_ok=True)
    write_jsonl(TABLES / "media.jsonl", media_rows)
    write_jsonl(TABLES / "bboxes.jsonl", bbox_rows)
    write_jsonl(TABLES / "validation_errors.jsonl", errors)
    write_jsonl(TABLES / "exact_cross_split_duplicates.jsonl", [
        {"sha256": rows[0]["sha256"], "items": [{"media_id": row["media_id"], "split": row["source_split"], "file_name": row["file_name"]} for row in rows]}
        for rows in exact_cross_split_groups
    ])

    summary = {
        "manifest_version": "1.0.0",
        "source_id": "rf100-wine-labels",
        "counts": {
            "media": len(media_rows),
            "bboxes": len(bbox_rows),
            "categories": len(categories_by_id),
            "decode_ok": sum(row["decode_status"] == "ok" for row in media_rows),
            "decode_error_or_missing": sum(row["decode_status"] != "ok" for row in media_rows),
            "images_with_bboxes": sum(row["bbox_count"] > 0 for row in media_rows),
            "images_without_bboxes": sum(row["bbox_count"] == 0 for row in media_rows),
            "valid_bboxes": sum(row["validation_status"] == "valid" for row in bbox_rows),
            "invalid_bboxes": sum(row["validation_status"] != "valid" for row in bbox_rows),
            "validation_errors": len(errors),
            "exact_duplicate_groups": len(exact_duplicate_groups),
            "exact_cross_split_duplicate_groups": len(exact_cross_split_groups),
            "same_dhash_cross_split_groups": len(dhash_cross_split_groups),
        },
        "source_splits": dict(Counter(row["source_split"] for row in media_rows)),
        "categories": categories_by_id,
        "semantic_scope": {
            "bboxes_describe": "text/logo/attribute regions on wine labels",
            "bboxes_do_not_describe": "wine bottle extents or exact wine SKU identities",
            "russian_wine_filter": "not available from COCO annotations; OCR/manual review required",
        },
        "gates": {
            "all_images_decode": all(row["decode_status"] == "ok" for row in media_rows),
            "all_coco_images_accounted_for": not any(row["type"] in {"missing_image", "orphan_image"} for row in errors),
            "all_bboxes_valid": all(row["validation_status"] == "valid" for row in bbox_rows),
            "safe_to_reuse_upstream_splits_without_leakage_review": not exact_cross_split_groups and not dhash_cross_split_groups,
            "exact_russian_wine_labels_available": False,
        },
    }
    write_json(TABLES / "SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["gates"]["all_images_decode"] and summary["gates"]["all_bboxes_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
