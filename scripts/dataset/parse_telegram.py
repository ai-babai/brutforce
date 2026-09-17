from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

import pdfplumber
from lxml import html

from common import IMAGE_EXTENSIONS, image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


def normalize_text(value: str) -> str:
    return " ".join(TOKEN_RE.findall(value.lower().replace("ё", "е")))


def significant_tokens(value: str) -> set[str]:
    stop = {
        "вино", "вина", "белое", "красное", "розовое", "сухое", "полусухое",
        "полусладкое", "сладкое", "игристое", "брют", "экстра", "россия",
        "резерв", "reserve", "коллекция", "куве", "cuvee", "классик", "classic",
        "каберне", "совиньон", "мерло", "рислинг", "шардоне", "саперави",
        "сира", "шираз", "пино", "нуар", "блан", "мускат", "алиготе",
        "ркацители", "красностоп", "цимлянский", "кокур", "темпранильо",
        "мальбек", "вионье", "траминер", "гевюрцтраминер", "пти", "вердо",
    }
    return {token for token in normalize_text(value).split() if len(token) >= 4 and token not in stop}


def load_products(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def product_candidates(text: str, products: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized = normalize_text(text)
    text_tokens = set(normalized.split())
    candidates: list[dict[str, object]] = []
    if len(normalized) < 4:
        return candidates
    for product in products:
        name = str(product.get("wine_name") or "")
        winery = str(product.get("winery") or "")
        name_norm = normalize_text(name)
        winery_norm = normalize_text(winery)
        name_tokens = significant_tokens(name)
        matched_name_tokens = name_tokens & text_tokens
        exact_name = bool(name_tokens) and len(name_norm) >= 7 and name_norm in normalized
        winery_match = len(winery_norm) >= 4 and winery_norm in normalized
        coverage = len(matched_name_tokens) / max(1, len(name_tokens))
        if exact_name:
            score = 0.9 + (0.05 if winery_match else 0.0)
            method = "exact_normalized_wine_name"
        elif winery_match and len(matched_name_tokens) >= 1 and coverage >= 0.5:
            score = min(0.89, 0.55 + 0.25 * coverage + 0.09)
            method = "winery_and_name_token_overlap"
        elif len(matched_name_tokens) >= 2 and coverage >= 0.75:
            score = min(0.84, 0.5 + 0.4 * coverage)
            method = "name_token_overlap"
        else:
            continue
        candidates.append(
            {
                "product_id": product.get("product_id"),
                "slug": product.get("slug"),
                "score": round(score, 4),
                "method": method,
                "matched_tokens": sorted(matched_name_tokens),
            }
        )
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["slug"])))
    return candidates[:25]


def extract_messages(html_path: Path, export_root: Path) -> tuple[list[dict[str, object]], dict[str, list[str]]]:
    document = html.fromstring(html_path.read_bytes())
    nodes = document.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' message ')]")
    messages: list[dict[str, object]] = []
    path_to_messages: dict[str, list[str]] = defaultdict(list)
    for index, node in enumerate(nodes):
        raw_id = node.get("id") or f"index_{index:06d}"
        message_id = stable_id("tg_message", raw_id)
        date_nodes = node.xpath(".//div[contains(concat(' ', normalize-space(@class), ' '), ' date ')][@title]")
        timestamp = date_nodes[0].get("title") if date_nodes else None
        text_nodes = node.xpath(".//div[contains(concat(' ', normalize-space(@class), ' '), ' text ')]")
        message_text = "\n".join(part.text_content().strip() for part in text_nodes if part.text_content().strip())
        referenced_paths: list[str] = []
        for href in node.xpath(".//a[@href]/@href"):
            href = unquote(str(href)).replace("\\", "/")
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            candidate = (export_root / href).resolve()
            try:
                relative = candidate.relative_to(export_root.resolve()).as_posix()
            except ValueError:
                continue
            if candidate.is_file():
                referenced_paths.append(relative)
                path_to_messages[relative].append(message_id)
        record = {
            "message_id": message_id,
            "source_message_key": raw_id,
            "sequence": index,
            "timestamp_raw": timestamp,
            "has_text": bool(message_text),
            "text_length": len(message_text),
            "text_sha256": hashlib.sha256(message_text.encode("utf-8")).hexdigest() if message_text else None,
            "referenced_paths": sorted(set(referenced_paths)),
            "private_text": message_text,
        }
        messages.append(record)
    return messages, path_to_messages


def media_role(path: Path, export_root: Path) -> tuple[str, bool]:
    relative = path.relative_to(export_root)
    top = relative.parts[0].lower() if relative.parts else ""
    lower_name = path.name.lower()
    thumbnail = "_thumb" in lower_name or lower_name.endswith(".pdf_thumb.jpg")
    if top == "photos":
        return ("derived_thumbnail" if thumbnail else "telegram_photo", thumbnail)
    if top == "files":
        return ("derived_thumbnail" if thumbnail else "telegram_file_image", thumbnail)
    if top == "images":
        return ("telegram_export_ui_asset", thumbnail)
    return ("other_image", thumbnail)


def parse_pdfs(pdf_files: list[Path], dataset_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    documents: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []
    for pdf_index, path in enumerate(pdf_files, start=1):
        relative_path = relative_posix(path, dataset_root)
        document_id = stable_id("tg_pdf", relative_path)
        document = {
            "document_id": document_id,
            "relative_path": relative_path,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "parse_status": "error",
            "page_count": None,
            "pages_with_text": 0,
            "tables_found": 0,
            "table_rows_found": 0,
            "parse_error": None,
        }
        try:
            with pdfplumber.open(path) as pdf:
                document["page_count"] = len(pdf.pages)
                for page_number, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        document["pages_with_text"] += 1
                    tables = page.extract_tables() or []
                    document["tables_found"] += len(tables)
                    for table_index, table in enumerate(tables):
                        for row_index, cells in enumerate(table):
                            cleaned_cells = [
                                re.sub(r"\s+", " ", cell).strip() if isinstance(cell, str) else None
                                for cell in cells
                            ]
                            if not any(cleaned_cells):
                                continue
                            table_rows.append(
                                {
                                    "document_id": document_id,
                                    "page": page_number,
                                    "table": table_index,
                                    "row": row_index,
                                    "cells": cleaned_cells,
                                    "non_empty_cells": sum(bool(cell) for cell in cleaned_cells),
                                }
                            )
                            document["table_rows_found"] += 1
            document["parse_status"] = "ok"
        except Exception as exc:
            document["parse_error"] = f"{type(exc).__name__}: {exc}"[:500]
        documents.append(document)
        print(f"Parsed PDF {pdf_index}/{len(pdf_files)}", flush=True)
    return documents, table_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse Telegram export media, messages and PDF score tables.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    dataset_root = project_root / "Dataset"
    dataset_dir = dataset_root / "02_rvk_telegram"
    export_root = dataset_root / "00_raw" / "02_rvk_telegram" / "ChatExport_2026-09-15"
    html_path = export_root / "messages.html"
    tables_dir = dataset_dir / "tables"
    private_cache = dataset_dir / "cache"
    if not html_path.is_file():
        raise FileNotFoundError(html_path)

    messages, path_to_messages = extract_messages(html_path, export_root)
    products = load_products(dataset_root / "01_svoe_vino_catalog" / "tables" / "products.jsonl")
    # Telegram albums store the caption only on the first item.  Propagate it
    # solely to immediately following media messages with the exact timestamp;
    # this creates event-level candidates, never an automatic SKU label.
    album_anchor_by_timestamp: dict[str, dict[str, object]] = {}
    for message in messages:
        own_text = str(message.get("private_text") or "")
        timestamp = str(message.get("timestamp_raw") or "")
        has_media = bool(message.get("referenced_paths"))
        if own_text and timestamp and has_media:
            album_anchor_by_timestamp[timestamp] = message
            message["context_source_message_id"] = message["message_id"]
            message["context_text"] = own_text
        elif not own_text and timestamp and has_media and timestamp in album_anchor_by_timestamp:
            anchor = album_anchor_by_timestamp[timestamp]
            if int(message["sequence"]) - int(anchor["sequence"]) <= 30:
                message["context_source_message_id"] = anchor["message_id"]
                message["context_text"] = str(anchor.get("private_text") or "")
            else:
                message["context_source_message_id"] = None
                message["context_text"] = ""
        else:
            message["context_source_message_id"] = message["message_id"] if own_text else None
            message["context_text"] = own_text
    message_candidates: dict[str, list[dict[str, object]]] = {}
    private_messages: list[dict[str, object]] = []
    public_messages: list[dict[str, object]] = []
    for message in messages:
        private_text = str(message.pop("private_text"))
        context_text = str(message.pop("context_text"))
        candidates = product_candidates(context_text, products)
        message_candidates[str(message["message_id"])] = candidates
        private_messages.append({**message, "text": private_text, "context_text": context_text, "product_candidates": candidates})
        public_messages.append({**message, "product_candidate_count": len(candidates)})

    image_files = sorted(
        path for path in export_root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    media_records: list[dict[str, object]] = []
    hash_to_media: dict[str, list[str]] = defaultdict(list)
    for index, path in enumerate(image_files, start=1):
        relative_to_export = path.relative_to(export_root).as_posix()
        relative_path = relative_posix(path, dataset_root)
        role, is_thumbnail = media_role(path, export_root)
        media_id = stable_id("media_tg", relative_path)
        digest = sha256_file(path)
        probe = image_probe(path, calculate_dhash=not is_thumbnail and role in {"telegram_photo", "telegram_file_image"})
        message_ids = sorted(set(path_to_messages.get(relative_to_export, [])))
        candidate_lists = [message_candidates.get(message_id, []) for message_id in message_ids]
        candidate_map: dict[str, dict[str, object]] = {}
        for candidates in candidate_lists:
            for candidate in candidates:
                product_id = str(candidate["product_id"])
                previous = candidate_map.get(product_id)
                if previous is None or float(candidate["score"]) > float(previous["score"]):
                    candidate_map[product_id] = candidate
        candidates = sorted(candidate_map.values(), key=lambda item: (-float(item["score"]), str(item["slug"])))
        if is_thumbnail:
            label_status = "derived_thumbnail_excluded"
            bbox_status = "not_applicable"
        elif role in {"telegram_photo", "telegram_file_image"}:
            label_status = "candidate_from_caption_unverified" if candidates else "unlabeled"
            bbox_status = "missing_scene_audit"
        else:
            label_status = "out_of_scope_export_asset"
            bbox_status = "not_applicable"
        record = {
            "manifest_version": "1.0.0",
            "source_id": "rvk-telegram-2026-09-15",
            "media_id": media_id,
            "relative_path": relative_path,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "source_role": role,
            "is_thumbnail": is_thumbnail,
            "message_ids": message_ids,
            "product_candidates": candidates,
            "product_id": None,
            "association_grade": "bronze" if candidates else None,
            "label_status": label_status,
            "bbox_status": bbox_status,
            "training_candidate": False,
            **probe,
        }
        media_records.append(record)
        hash_to_media[digest].append(media_id)
        if index % 100 == 0:
            print(f"Audited {index}/{len(image_files)} Telegram images", flush=True)

    for record in media_records:
        duplicate_ids = hash_to_media[str(record["sha256"])]
        record["exact_duplicate_group_id"] = (
            stable_id("exact", str(record["sha256"])) if len(duplicate_ids) > 1 else None
        )

    association_candidates: list[dict[str, object]] = []
    for record in media_records:
        for candidate in record["product_candidates"]:
            association_candidates.append(
                {
                    "association_id": stable_id("assoc", f"{record['media_id']}:{candidate['product_id']}"),
                    "media_id": record["media_id"],
                    "message_ids": record["message_ids"],
                    "product_id": candidate["product_id"],
                    "slug": candidate["slug"],
                    "grade": "bronze",
                    "method": candidate["method"],
                    "score": candidate["score"],
                    "eligible_for_supervised_training": False,
                    "review_status": "pending_visual_verification",
                }
            )

    pdf_files = sorted((export_root / "files").glob("*.pdf"))
    pdf_documents, pdf_table_rows = parse_pdfs(pdf_files, dataset_root)

    counts = {
        "messages": write_jsonl(tables_dir / "messages.jsonl", public_messages),
        "private_messages": write_jsonl(private_cache / "messages_private.jsonl", private_messages),
        "media": write_jsonl(tables_dir / "media.jsonl", media_records),
        "association_candidates": write_jsonl(tables_dir / "association_candidates.jsonl", association_candidates),
        "pdf_documents": write_jsonl(tables_dir / "pdf_documents.jsonl", pdf_documents),
        "pdf_table_rows": write_jsonl(tables_dir / "pdf_table_rows.jsonl", pdf_table_rows),
    }
    scene_images = [record for record in media_records if record["source_role"] in {"telegram_photo", "telegram_file_image"} and not record["is_thumbnail"]]
    summary = {
        "manifest_version": "1.0.0",
        "source_id": "rvk-telegram-2026-09-15",
        "counts": {
            **counts,
            "products_available_for_caption_matching": len(products),
            "images_decode_ok": sum(record["decode_status"] == "ok" for record in media_records),
            "images_decode_error": sum(record["decode_status"] != "ok" for record in media_records),
            "scene_images": len(scene_images),
            "scene_images_with_caption_candidates": sum(bool(record["product_candidates"]) for record in scene_images),
            "scene_images_with_verified_product_label": 0,
            "scene_images_with_bbox_annotations": 0,
            "exact_duplicate_groups": sum(len(ids) > 1 for ids in hash_to_media.values()),
            "pdf_parse_ok": sum(document["parse_status"] == "ok" for document in pdf_documents),
            "pdf_parse_error": sum(document["parse_status"] != "ok" for document in pdf_documents),
        },
        "distributions": {
            "source_roles": Counter(str(record["source_role"]) for record in media_records),
            "label_status": Counter(str(record["label_status"]) for record in media_records),
            "image_formats": Counter(str(record["image_format"]) for record in media_records),
        },
        "gates": {
            "all_images_accounted_for": len(media_records) == len(image_files),
            "all_pdfs_accounted_for": len(pdf_documents) == len(pdf_files),
            "supervised_training_ready": False,
            "blockers": [
                "visual verification of caption-to-product candidates",
                "bbox annotation for multi-bottle and shelf scenes",
                "event segmentation and cumulative score-table deduplication",
                "participant/media usage terms confirmation",
            ],
        },
    }
    write_json(tables_dir / "SUMMARY.json", summary)
    print(f"PASS: parsed {len(messages)} messages, {len(media_records)} images and {len(pdf_documents)} PDFs", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
