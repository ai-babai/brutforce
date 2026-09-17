#!/usr/bin/env python3
"""Capture and parse the public Svoe Vino wine catalogue.

The crawler only requests URLs listed in the public wine sitemap.  It does not
call the site's /api routes, which are disallowed by robots.txt.  Responses are
cached atomically, so an interrupted crawl can be resumed without redownloading
successful pages.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html as html_lib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from lxml import html

from common import write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE = ROOT / "Dataset/00_raw/04_svoe_vino_web_snapshots/2026-09-15"
OUTPUT = ROOT / "Dataset/04_svoe_vino_web_enrichment/tables"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 "
    "VinoDatasetResearch/1.0"
)
BLOCK_MARKERS = ("qrator", "checking your browser", "access denied")
ASSET_HASH_RE = re.compile(r"_[0-9a-f]{10}$", re.I)
VARIANT_RE = re.compile(r"^(thumbnail|small|medium|large)_", re.I)
UPLOAD_RE = re.compile(r"/uploads/([^?\"'<> ]+)", re.I)


class PoliteGate:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self) -> None:
        with self.lock:
            delay = self.interval - (time.monotonic() - self.last)
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", html_lib.unescape(value)).strip()
    return value or None


def asset_key(name_or_url: str | None) -> str | None:
    if not name_or_url:
        return None
    path = urllib.parse.urlsplit(name_or_url).path
    name = urllib.parse.unquote(Path(path).name)
    stem = Path(name).stem
    stem = VARIANT_RE.sub("", stem)
    stem = ASSET_HASH_RE.sub("", stem)
    normalized = re.sub(r"[^0-9a-zа-яё]+", "", stem.casefold())
    return normalized or None


def sitemap_urls(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    urls = []
    for element in root.iter():
        if element.tag.endswith("loc") and element.text:
            url = element.text.strip()
            if url.startswith("https://vino-svoe.ru/wines/"):
                urls.append(url)
    return sorted(set(urls))


def fetch_one(url: str, pages: Path, gate: PoliteGate, retries: int) -> dict:
    slug = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1])
    target = pages / f"{slug}.html"
    if target.exists() and target.stat().st_size > 10_000:
        payload = target.read_bytes()
        return {"url": url, "slug": slug, "status": "cached", "bytes": len(payload), "sha256": sha256_bytes(payload)}

    error = None
    for attempt in range(1, retries + 1):
        try:
            gate.wait()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
                status_code = int(getattr(response, "status", 200))
            lower = payload[:100_000].lower()
            if status_code != 200 or len(payload) < 10_000 or any(marker.encode() in lower for marker in BLOCK_MARKERS):
                raise RuntimeError(f"unexpected response: status={status_code}, bytes={len(payload)}")
            temp = target.with_suffix(target.suffix + f".{os.getpid()}.part")
            temp.write_bytes(payload)
            temp.replace(target)
            return {"url": url, "slug": slug, "status": "downloaded", "bytes": len(payload), "sha256": sha256_bytes(payload)}
        except Exception as exc:  # recorded verbatim in private operational manifest
            error = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 12))
    return {"url": url, "slug": slug, "status": "error", "error": error}


def meta_content(tree, *, name: str | None = None, prop: str | None = None) -> str | None:
    if name:
        values = tree.xpath(f'//meta[@name="{name}"]/@content')
    else:
        values = tree.xpath(f'//meta[@property="{prop}"]/@content')
    return clean_text(values[0]) if values else None


def first_text(tree, xpath: str) -> str | None:
    values = tree.xpath(xpath)
    if not values:
        return None
    value = values[0]
    if hasattr(value, "text_content"):
        value = value.text_content()
    return clean_text(str(value))


def parse_page(path: Path, url: str, archive_by_key: dict[str, list[dict]]) -> dict:
    payload = path.read_bytes()
    tree = html.fromstring(payload)
    title = first_text(tree, '(//h1[contains(concat(" ", normalize-space(@class), " "), " wine-main-title-block__title ")])[1]')
    manufacturer = first_text(tree, '(//a[contains(concat(" ", normalize-space(@class), " "), " wine-main-title-block__manufacturer ")])[1]')
    hero_images = tree.xpath('//img[contains(@class,"wine-hero-block__bottle") or contains(@class,"wine-mobile-hero-block__bottle")]/@src')
    og_image = meta_content(tree, prop="og:image")
    candidates = [str(value) for value in hero_images]
    if og_image:
        candidates.append(og_image)
    upload_names = []
    seen = set()
    for value in candidates:
        match = UPLOAD_RE.search(value)
        if match:
            name = urllib.parse.unquote(match.group(1))
            if name not in seen:
                seen.add(name)
                upload_names.append(name)
    primary_url = candidates[0] if candidates else og_image
    primary_name = upload_names[0] if upload_names else None
    key = asset_key(primary_name)
    archive_matches = archive_by_key.get(key or "", [])
    slug = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1])
    blocked = any(marker in payload[:100_000].lower().decode("utf-8", "ignore") for marker in BLOCK_MARKERS)
    parse_status = "ok" if title and primary_name and not blocked else "incomplete_or_blocked"
    return {
        "source_id": "svoe-vino-live-2026-09-15",
        "page_url": url,
        "slug": slug,
        "page_sha256": sha256_bytes(payload),
        "page_bytes": len(payload),
        "parse_status": parse_status,
        "title": title,
        "manufacturer": manufacturer,
        "meta_description": meta_content(tree, name="description"),
        "og_title": meta_content(tree, prop="og:title"),
        "primary_image_url": primary_url,
        "primary_upload_name": primary_name,
        "primary_asset_key": key,
        "archive_media_matches": [m["media_id"] for m in archive_matches],
        "archive_media_match_count": len(archive_matches),
        "all_page_upload_names": upload_names,
    }


def load_archive_media(path: Path) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("asset_key")
            if key:
                result.setdefault(key, []).append(row)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--interval", type=float, default=0.35, help="Minimum seconds between requests across all workers")
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    capture = args.capture_dir.resolve()
    sitemap = capture / "wines-sitemap.xml"
    robots = capture / "robots.txt"
    if not sitemap.exists() or not robots.exists():
        raise SystemExit("robots.txt and wines-sitemap.xml must be captured before crawling")
    robots_text = robots.read_text(encoding="utf-8", errors="replace")
    if "Disallow: /api/*" not in robots_text:
        raise SystemExit("robots policy changed; review before crawling")
    urls = sitemap_urls(sitemap)
    pages = capture / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    gate = PoliteGate(args.interval)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futures = [pool.submit(fetch_one, url, pages, gate, args.retries) for url in urls]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(future.result())
            if index % 100 == 0 or index == len(futures):
                counts = Counter(item["status"] for item in results)
                print(f"Fetched {index}/{len(futures)}: {dict(counts)}", flush=True)
    results.sort(key=lambda row: row["slug"])
    write_jsonl(capture / "crawl_manifest.jsonl", results)

    archive_by_key = load_archive_media(ROOT / "Dataset/01_svoe_vino_catalog/tables/media.jsonl")
    pages_by_slug = {row["slug"]: row for row in results if row["status"] != "error"}
    parsed = []
    parse_errors = []
    for url in urls:
        slug = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/").split("/")[-1])
        if slug not in pages_by_slug:
            continue
        try:
            parsed.append(parse_page(pages / f"{slug}.html", url, archive_by_key))
        except Exception as exc:
            parse_errors.append({"slug": slug, "url": url, "error": f"{type(exc).__name__}: {exc}"})
    parsed.sort(key=lambda row: row["slug"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUTPUT / "live_products.jsonl", parsed)
    write_jsonl(OUTPUT / "parse_errors.jsonl", parse_errors)

    archive_products = {}
    products_path = ROOT / "Dataset/01_svoe_vino_catalog/tables/products.jsonl"
    if products_path.exists():
        with products_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    archive_products[row["slug"]] = row
    live_slugs = {row["slug"] for row in parsed}
    archive_slugs = set(archive_products)
    missing_assets = [row for row in parsed if row["parse_status"] == "ok" and row["archive_media_match_count"] == 0]
    summary = {
        "manifest_version": "1.0.0",
        "source_id": "svoe-vino-live-2026-09-15",
        "capture_date": "2026-09-15",
        "counts": {
            "sitemap_urls": len(urls),
            "pages_available": len(pages_by_slug),
            "fetch_errors": sum(row["status"] == "error" for row in results),
            "parsed_products": len(parsed),
            "parse_errors": len(parse_errors),
            "parse_incomplete_or_blocked": sum(row["parse_status"] != "ok" for row in parsed),
            "live_products_with_archive_asset": sum(row["archive_media_match_count"] > 0 for row in parsed),
            "live_products_without_archive_asset": len(missing_assets),
            "live_slugs_new_vs_archive": len(live_slugs - archive_slugs),
            "archive_slugs_absent_live": len(archive_slugs - live_slugs),
        },
        "new_live_slugs": sorted(live_slugs - archive_slugs),
        "archive_only_slugs": sorted(archive_slugs - live_slugs),
        "missing_archive_assets": [
            {"slug": row["slug"], "title": row["title"], "primary_image_url": row["primary_image_url"]}
            for row in missing_assets
        ],
        "gates": {
            "all_sitemap_pages_captured": len(pages_by_slug) == len(urls),
            "all_captured_pages_parsed": not parse_errors and all(row["parse_status"] == "ok" for row in parsed),
            "all_live_primary_assets_present_in_archive": not missing_assets,
        },
    }
    write_json(OUTPUT / "SUMMARY.json", summary)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))
    return 0 if summary["gates"]["all_sitemap_pages_captured"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
