from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import duckdb

from common import stable_id, write_json, write_jsonl


RUSSIAN_REGION_MARKERS = ("russia", "russian", "crimea", "krasnodar", "kuban", "rostov", "dagestan")
KNOWN_RUSSIAN_BRAND_MARKERS = (
    "abrau durso", "abrau dyurso", "aristov", "fanagoria", "massandra", "inkerman",
    "chateau tamagne", "golubitskoe", "vedernikov", "gai kodzor", "gay kodzor",
    "alma valley", "sikory", "lefkadia", "usadba divnomorskoe", "zolotaya balka",
    "kuban vino", "new world crimea", "novy svet", "novyi svet",
)
CYRILLIC = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})
GENERIC_TOKENS = {
    "wine", "wines", "winery", "vino", "vin", "vinodelnya", "estate", "chateau", "domaine", "domain", "reserve",
    "vineyard", "vineyards", "organic", "valley", "barrel", "one", "new", "pays",
    "collection", "classic", "premium", "limited", "edition", "select", "special",
    "red", "white", "rose", "rosé", "dry", "semi", "sweet", "brut", "extra",
    "sparkling", "still", "blend", "cuvee", "cuvée", "cabernet", "sauvignon", "merlot",
    "pinot", "noir", "gris", "blanc", "chardonnay", "riesling", "saperavi", "muscat",
    "syrah", "shiraz", "tempranillo", "malbec", "year", "cotes", "cote", "petit", "grand", "clos", "sur", "des", "del", "collection", "krasnoe", "beloe",
    "rozovoe", "suhoe", "polusuhoe", "polusladkoe", "sladkoe", "igristoe", "bryut",
}


def normalized_tokens(value: object) -> set[str]:
    text = str(value or "").casefold().translate(CYRILLIC)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return {
        token for token in re.findall(r"[a-z0-9]+", text)
        if len(token) >= 3 and token not in GENERIC_TOKENS and not token.isdigit()
    }


def transliteration_variants(tokens: set[str]) -> set[str]:
    variants = set(tokens)
    for token in list(tokens):
        variants.add(token.replace("dyu", "du"))
        variants.add(token.replace("yu", "u"))
        variants.add(token.replace("ya", "ia"))
        variants.add(token.replace("kh", "h"))
        variants.add(token.replace("iy", "i"))
    return {token for token in variants if len(token) >= 3}


def load_catalog(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            winery_tokens = transliteration_variants(normalized_tokens(row.get("winery")))
            title_tokens = normalized_tokens(row.get("wine_name"))
            slug_tokens = normalized_tokens(str(row.get("slug") or "").replace("-", " "))
            rows.append({
                "product_id": row.get("product_id"), "slug": row.get("slug"),
                "wine_name": row.get("wine_name"), "winery": row.get("winery"),
                "winery_tokens": winery_tokens, "title_tokens": title_tokens,
                "all_tokens": slug_tokens | winery_tokens | title_tokens,
            })
    return rows


def catalog_matches(name: object, catalog: list[dict[str, object]]) -> list[dict[str, object]]:
    tokens = normalized_tokens(name)
    matches = []
    if not tokens:
        return matches
    for item in catalog:
        winery_overlap = tokens & item["winery_tokens"]
        title_overlap = tokens & item["title_tokens"]
        all_overlap = tokens & item["all_tokens"]
        if not winery_overlap:
            continue
        if len(all_overlap) < 2 and not (len(winery_overlap) >= 2):
            continue
        score = round((3 * len(winery_overlap) + 2 * len(title_overlap) + len(all_overlap)) / max(1, len(tokens) + 5), 4)
        matches.append({
            "product_id": item["product_id"], "slug": item["slug"],
            "catalog_wine_name": item["wine_name"], "catalog_winery": item["winery"],
            "shared_tokens": sorted(all_overlap), "score": score,
        })
    return sorted(matches, key=lambda row: (-row["score"], row["slug"]))[:5]


def shard_for_id(image_id: str, metadata: dict[str, object]) -> str | None:
    match = re.fullmatch(r"wine_(\d+)", image_id)
    if not match:
        return None
    number = int(match.group(1))
    for shard in metadata.get("shards", []):
        start = int(re.search(r"(\d+)", shard["start_image"]).group(1))
        end = int(re.search(r"(\d+)", shard["end_image"]).group(1))
        if start <= number <= end:
            return str(shard["shard_path"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter Wine Images 126K metadata to Russian-region candidates.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    raw_dir = project_root / "Dataset" / "00_raw" / "06_wine_images_126k"
    output_dir = project_root / "Dataset" / "06_wine_images_126k" / "tables"
    parquet_path = raw_dir / "wine_text_126k.parquet"
    shard_metadata_path = raw_dir / "shard_metadata.json"
    if not parquet_path.is_file() or not shard_metadata_path.is_file():
        raise FileNotFoundError("Wine Images metadata inputs are incomplete")

    connection = duckdb.connect()
    columns = [row[0] for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(parquet_path)]).fetchall()]
    rows = connection.execute("SELECT * FROM read_parquet(?)", [str(parquet_path)]).fetchall()
    shard_metadata = json.loads(shard_metadata_path.read_text(encoding="utf-8"))
    catalog = load_catalog(project_root / "Dataset/01_svoe_vino_catalog/tables/products.jsonl")

    region_counts: Counter[str] = Counter()
    candidates: list[dict[str, object]] = []
    for values in rows:
        row = dict(zip(columns, values))
        region = str(row.get("region") or "").strip().lower()
        region_counts[region or "<missing>"] += 1
        markers = [marker for marker in RUSSIAN_REGION_MARKERS if marker in region]
        normalized_name = " ".join(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(row.get("name") or "").casefold()).encode("ascii", "ignore").decode("ascii")))
        brand_markers = [marker for marker in KNOWN_RUSSIAN_BRAND_MARKERS if marker in normalized_name]
        matches = catalog_matches(row.get("name"), catalog)
        if not markers and not brand_markers and not matches:
            continue
        image_id = str(row.get("image_id") or row.get("id") or "")
        candidates.append(
            {
                "manifest_version": "1.0.0",
                "source_id": "wine-images-126k-hf",
                "external_id": row.get("id"),
                "image_id": image_id,
                "wine_name": row.get("name"),
                "description": row.get("description"),
                "category": row.get("category"),
                "region": row.get("region"),
                "price": row.get("price"),
                "russian_region_markers": markers,
                "known_russian_brand_markers": brand_markers,
                "catalog_match_candidates": matches,
                "selection_evidence": "region_marker" if markers else ("known_russian_brand_marker" if brand_markers else "catalog_name_alias"),
                "candidate_id": stable_id("hf126k_candidate", image_id),
                "required_image_shard": shard_for_id(image_id, shard_metadata),
                "review_status": "pending_country_producer_and_visual_verification",
                "product_id": None,
                "label_status": "external_image_level_name",
            }
        )

    write_jsonl(output_dir / "russian_region_candidates.jsonl", candidates)
    required_shards = sorted({str(item["required_image_shard"]) for item in candidates if item["required_image_shard"]})
    summary = {
        "source_rows": len(rows),
        "candidates": len(candidates),
        "region_marker_candidates": sum(item["selection_evidence"] == "region_marker" for item in candidates),
        "catalog_alias_candidates": sum(item["selection_evidence"] == "catalog_name_alias" for item in candidates),
        "known_russian_brand_candidates": sum(item["selection_evidence"] == "known_russian_brand_marker" for item in candidates),
        "required_image_shards": required_shards,
        "top_regions": region_counts.most_common(100),
        "filters": list(RUSSIAN_REGION_MARKERS),
        "known_russian_brand_markers": list(KNOWN_RUSSIAN_BRAND_MARKERS),
        "catalog_alias_method": "requires winery-token overlap and at least two distinctive shared tokens; all results remain review candidates",
        "images_downloaded": 0,
        "bbox_annotations": 0,
        "gates": {
            "candidate_metadata_ready": True,
            "images_ready": False,
            "catalog_identity_ready": False,
        },
    }
    write_json(output_dir / "FILTER-SUMMARY.json", summary)
    print(f"PASS: selected {len(candidates)} candidates from {len(rows)} text rows", flush=True)
    print(f"Required shards: {len(required_shards)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
