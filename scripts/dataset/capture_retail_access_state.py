#!/usr/bin/env python3
"""Capture public access-policy endpoints without evading site protections."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DATE = str(date.today())
USER_AGENT = "VinoResearchBot/0.1 (+noncommercial dataset provenance audit)"
TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 2

SOURCES = {
    "12_krasnoe_i_beloe_ru_wines": {
        "base_url": "https://krasnoeibeloe.ru/",
        "probes": [
            ("robots", "https://krasnoeibeloe.ru/robots.txt"),
            ("sitemap", "https://krasnoeibeloe.ru/sitemap.xml"),
            ("sample_product", "https://krasnoeibeloe.ru/catalog/vino/vino_kyanti_rizerva_kr_p_sukh/"),
        ],
        "stop_after_robots_failure": True,
    },
    "13_winelab_ru_wines": {
        "base_url": "https://www.winelab.ru/",
        "probes": [
            ("robots", "https://www.winelab.ru/robots.txt"),
            ("sitemap", "https://www.winelab.ru/sitemap.xml"),
            ("sample_product", "https://www.winelab.ru/product/1019959"),
        ],
        "stop_after_robots_failure": True,
    },
    "14_simplewine_ru_wines": {
        "base_url": "https://simplewine.ru/",
        "probes": [
            ("robots", "https://simplewine.ru/robots.txt"),
            ("sitemap", "https://simplewine.ru/sitemap/sitemaps.xml"),
        ],
        "stop_after_robots_failure": True,
    },
    "17_luding_ru_wines": {
        "base_url": "https://luding.ru/",
        "probes": [
            ("robots", "https://luding.ru/robots.txt"),
            ("sitemap", "https://luding.ru/sitemap.xml"),
        ],
        "stop_after_robots_failure": True,
    },
}


def safe_name(label: str, content_type: str | None, status: int | None) -> str:
    suffix = ".xml" if content_type and "xml" in content_type else ".txt"
    if status and status >= 400:
        return f"{label}.http-{status}{suffix}"
    return f"{label}{suffix}"


def fetch(url: str) -> tuple[dict, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read()
            return {
                "status": response.status,
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type"),
                "retry_after": response.headers.get("Retry-After"),
                "error": None,
            }, body
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return {
            "status": exc.code,
            "final_url": exc.geturl(),
            "content_type": exc.headers.get("Content-Type"),
            "retry_after": exc.headers.get("Retry-After"),
            "error": f"HTTPError: {exc.reason}",
        }, body
    except Exception as exc:
        return {
            "status": None,
            "final_url": None,
            "content_type": None,
            "retry_after": None,
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }, b""


def main() -> int:
    for dataset, config in SOURCES.items():
        raw = ROOT / "Dataset/00_raw" / dataset / CAPTURE_DATE
        tables = ROOT / "Dataset" / dataset / "tables"
        raw.mkdir(parents=True, exist_ok=True)
        tables.mkdir(parents=True, exist_ok=True)
        results = []
        robots_ok = False

        for index, (label, url) in enumerate(config["probes"]):
            if index and config["stop_after_robots_failure"] and not robots_ok:
                results.append({
                    "probe": label,
                    "url": url,
                    "status": None,
                    "fetch_state": "not_requested_after_robots_failure",
                })
                continue

            metadata, body = fetch(url)
            status = metadata["status"]
            robots_ok = label != "robots" or (status is not None and 200 <= status < 300)
            record = {
                "probe": label,
                "url": url,
                **metadata,
                "fetch_state": "captured" if body else "failed_without_body",
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest() if body else None,
            }
            if body:
                filename = safe_name(label, metadata["content_type"], status)
                (raw / filename).write_bytes(body)
                record["relative_path"] = (raw / filename).relative_to(ROOT / "Dataset").as_posix()
            results.append(record)

            if status in {401, 403, 429}:
                break
            time.sleep(REQUEST_DELAY_SECONDS)

        summary = {
            "source_dataset": dataset,
            "capture_date": CAPTURE_DATE,
            "base_url": config["base_url"],
            "user_agent": USER_AGENT,
            "timeout_seconds": TIMEOUT_SECONDS,
            "request_delay_seconds": REQUEST_DELAY_SECONDS,
            "evasion_used": False,
            "probes": results,
        }
        (tables / "ACCESS-SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "dataset": dataset,
            "statuses": [row.get("status") for row in results],
            "states": [row.get("fetch_state") for row in results],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
