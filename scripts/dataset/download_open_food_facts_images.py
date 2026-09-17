#!/usr/bin/env python3
"""Download and audit selected Open Food Facts front images.

The downloader keeps all network bytes in 00_raw.  Exact product labels come
from the OFF barcode record; Russian-origin confidence remains a separate field.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from common import image_probe, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "Dataset/10_open_food_facts_wine_ru/tables"
RAW_IMAGES = ROOT / "Dataset/00_raw/10_open_food_facts_wine_ru/images"
SOURCE_BASE = "https://images.openfoodfacts.org/images/products"
USER_AGENT = "Vino-dataset-audit/1.0 (research; contact via local operator)"
SELECTED_STATUSES = {
    "silver_explicit_russian_origin",
    "silver_russian_brand_candidate",
    "bronze_probable_russian_needs_review",
}


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def product_path(code: str) -> str:
    normalized = "".join(char for char in str(code) if char.isdigit())
    if len(normalized) <= 8:
        return normalized
    groups = [normalized[index:index + 3] for index in range(0, len(normalized) - 4, 3)]
    groups.append(normalized[len(normalized) - 4:])
    return "/".join(groups)


def select_front(images: list[dict]) -> dict | None:
    candidates = [item for item in (images or []) if str(item.get("key") or "").startswith("front_")]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (
        str(item.get("key")) != "front_ru",
        -(int(item.get("sizes", {}).get("full", {}).get("h") or 0) * int(item.get("sizes", {}).get("full", {}).get("w") or 0)),
    ))
    return candidates[0]


def download(url: str, destination: Path) -> tuple[str, str | None]:
    if destination.is_file() and destination.stat().st_size > 0:
        return "cached", None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        temporary.replace(destination)
        time.sleep(0.15)
        return "downloaded", None
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        return "error", f"{type(exc).__name__}: {exc}"[:500]


def main() -> int:
    RAW_IMAGES.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(TABLES / "candidates.jsonl")
    media = []
    associations = []

    for row in rows:
        status = row.get("russian_wine_status")
        if status not in SELECTED_STATUSES:
            continue
        front = select_front(row.get("images") or [])
        if front is None or front.get("rev") is None:
            associations.append({
                "association_id": stable_id("assoc_off", str(row.get("code"))),
                "product_id": row["product_id"],
                "product_code": str(row.get("code") or ""),
                "media_id": None,
                "association_status": "no_selected_front_image",
                "russian_wine_status": status,
                "safe_for_supervised_sku": False,
            })
            continue

        code = str(row.get("code") or "")
        key = str(front["key"])
        rev = int(front["rev"])
        # The selected full image is the canonical OFF front crop and avoids
        # accidentally taking a back-label raw upload with the same product.
        url = f"{SOURCE_BASE}/{product_path(code)}/{key}.{rev}.full.jpg"
        destination = RAW_IMAGES / f"{code}__{key}__r{rev}.jpg"
        fetch_status, fetch_error = download(url, destination)
        probe = image_probe(destination, calculate_dhash=True) if destination.is_file() else {
            "decode_status": "not_downloaded", "decode_error": fetch_error,
            "image_format": None, "width": None, "height": None, "mode": None, "dhash64": None,
        }
        media_id = stable_id("media_off", f"{code}:{key}:{rev}")
        media_row = {
            "media_id": media_id,
            "product_id": row["product_id"],
            "product_code": code,
            "source_url": url,
            "raw_path": destination.relative_to(ROOT).as_posix(),
            "fetch_status": fetch_status,
            "fetch_error": fetch_error,
            "sha256": sha256_file(destination) if destination.is_file() else None,
            "bytes": destination.stat().st_size if destination.is_file() else None,
            "front_key": key,
            "front_revision": rev,
            "russian_wine_status": status,
            "russian_wine_status_reasons": row.get("russian_wine_status_reasons"),
            **probe,
        }
        media.append(media_row)
        associations.append({
            "association_id": stable_id("assoc_off", f"{code}:{media_id}"),
            "product_id": row["product_id"],
            "product_code": code,
            "media_id": media_id,
            "association_status": "exact_off_barcode_record",
            "russian_wine_status": status,
            "safe_for_supervised_sku": probe["decode_status"] == "ok",
            "label_scope": "exact OFF product/barcode; Russian-production confidence is separate",
        })

    write_jsonl(TABLES / "media.jsonl", media)
    write_jsonl(TABLES / "associations.jsonl", associations)
    status_counts = Counter(row.get("russian_wine_status") for row in rows)
    summary_path = TABLES / "SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["counts"].update({
        "selected_for_image_download": sum(status_counts[name] for name in SELECTED_STATUSES),
        "selected_front_images": len(media),
        "selected_products_without_front": sum(1 for item in associations if item["media_id"] is None),
        "downloaded_or_cached_images": sum(1 for item in media if item["fetch_status"] in {"downloaded", "cached"}),
        "decoded_images": sum(1 for item in media if item["decode_status"] == "ok"),
        "download_or_decode_errors": sum(1 for item in media if item["decode_status"] != "ok"),
    })
    duplicate_groups = defaultdict(list)
    for item in media:
        if item.get("sha256"):
            duplicate_groups[item["sha256"]].append(item["media_id"])
    summary["counts"]["exact_duplicate_groups"] = sum(1 for group in duplicate_groups.values() if len(group) > 1)
    summary["gates"].update({
        "images_downloaded_and_audited": all(item["decode_status"] == "ok" for item in media),
        "sku_labels_exact_to_off_record": all(item["association_status"] != "exact_off_barcode_record" or item["safe_for_supervised_sku"] for item in associations),
        "russian_origin_manually_verified": False,
    })
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["counts"]["download_or_decode_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
