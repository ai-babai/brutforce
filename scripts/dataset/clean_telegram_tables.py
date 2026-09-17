#!/usr/bin/env python3
"""Classify, deduplicate and catalog-match Telegram PDF table rows."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import write_json, write_jsonl
from parse_telegram import load_products, normalize_text, product_candidates


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Dataset"
TABLES = DATASET / "02_rvk_telegram/tables"

HEADER_WORDS = {
    "наименование", "производитель", "участник", "средняя оценка", "оценка из",
    "дата дегустации", "винодельня", "название", "место", "рейтинг",
}
DECIMAL_RE = re.compile(r"(?<!\d)(?:[2-5][,.]\d{1,2}|(?:7\d|8\d|9\d|100)[,.]?\d*)(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{4,}")


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def classify(text: str, cells: list[str | None]) -> str:
    normalized = normalize_text(text)
    non_empty = sum(bool(cell) for cell in cells)
    if non_empty <= 1 or len(normalized) < 4:
        return "structural_fragment"
    if any(word in normalized for word in HEADER_WORDS):
        return "header"
    has_word = bool(WORD_RE.search(text))
    has_score = bool(DECIMAL_RE.search(text))
    has_year = bool(YEAR_RE.search(text))
    if has_word and has_score and non_empty >= 3:
        return "score_row_candidate"
    if has_word and has_year and non_empty >= 3:
        return "wine_row_continuation_candidate"
    return "other_table_row"


def main() -> int:
    rows = read_jsonl(TABLES / "pdf_table_rows.jsonl")
    documents = read_jsonl(TABLES / "pdf_documents.jsonl")
    messages = read_jsonl(TABLES / "messages.jsonl")
    products = load_products(DATASET / "01_svoe_vino_catalog/tables/products.jsonl")

    document_by_id = {row["document_id"]: row for row in documents}
    pdf_messages = defaultdict(list)
    for message in messages:
        for path in message.get("referenced_paths", []):
            if str(path).casefold().endswith(".pdf"):
                pdf_messages[Path(path).name].append(message["message_id"])

    hash_frequency = Counter()
    prepared = []
    for row in rows:
        cells = row["cells"]
        normalized_cells = [normalize_text(str(cell or "")) for cell in cells]
        semantic = "\u241f".join(normalized_cells)
        digest = hashlib.sha256(semantic.encode("utf-8")).hexdigest()
        text = " | ".join(str(cell) for cell in cells if cell)
        row_class = classify(text, cells)
        matches = product_candidates(text, products) if row_class in {"score_row_candidate", "wine_row_continuation_candidate"} else []
        document = document_by_id[row["document_id"]]
        prepared.append({
            **row,
            "document_name": Path(document["relative_path"]).name,
            "message_ids": sorted(set(pdf_messages.get(Path(document["relative_path"]).name, []))),
            "semantic_sha256": digest,
            "row_class": row_class,
            "catalog_candidates": matches,
            "catalog_match_status": "candidate_unverified" if matches else "unmatched",
        })
        hash_frequency[digest] += 1

    seen = set()
    for row in prepared:
        digest = row["semantic_sha256"]
        row["exact_duplicate_count"] = hash_frequency[digest]
        row["dedupe_status"] = "canonical" if digest not in seen else "exact_duplicate_excluded"
        seen.add(digest)

    candidates = [
        row for row in prepared
        if row["row_class"] in {"score_row_candidate", "wine_row_continuation_candidate"}
        and row["dedupe_status"] == "canonical"
    ]
    write_jsonl(TABLES / "pdf_table_rows_clean.jsonl", prepared)
    write_jsonl(TABLES / "pdf_score_row_candidates.jsonl", candidates)
    summary = {
        "manifest_version": "1.0.0", "source_id": "rvk-telegram-2026-09-15",
        "counts": {
            "raw_rows": len(rows), "canonical_rows": sum(row["dedupe_status"] == "canonical" for row in prepared),
            "exact_duplicate_rows_excluded": sum(row["dedupe_status"] != "canonical" for row in prepared),
            "score_or_wine_row_candidates": len(candidates),
            "candidates_with_catalog_match": sum(bool(row["catalog_candidates"]) for row in candidates),
            "documents_linked_to_export_messages": len({row["document_id"] for row in prepared if row["message_ids"]}),
        },
        "class_distribution": dict(Counter(row["row_class"] for row in prepared)),
        "gates": {
            "exact_row_deduplication_complete": True,
            "logical_multiline_wine_rows_reconstructed": False,
            "catalog_matches_visually_verified": False,
            "safe_for_supervised_image_labels": False,
        },
        "blockers": [
            "PDF extraction splits some logical wine records across physical rows",
            "cumulative ranking documents repeat historical events with formatting changes",
            "table rows are not sufficient to assign individual bottles inside multi-bottle photos",
        ],
    }
    write_json(TABLES / "TABLE-CLEANING-SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
