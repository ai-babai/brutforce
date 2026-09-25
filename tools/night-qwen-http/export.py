"""Export a complete fresh HTTP capture to frozen-v2 and organizer scorers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--mode", choices=("service", "retrieval", "organizer"), required=True)
    p.add_argument("--suite", type=Path)
    p.add_argument("--submission-id")
    p.add_argument("--profile", choices=("uncapped", "projected-10s", "strict-10s",
                                          "rich-uncapped", "website-uncapped",
                                          "omp1-strict-10s", "website-strict-10s",
                                          "website-omp1-strict-10s"),
                   required=True)
    p.add_argument("--runtime-receipt", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.raw.read_text().splitlines() if line]
    by_id = {row["case_id"]: row for row in rows}
    if len(rows) != len(by_id) or len(rows) != 316:
        raise ValueError("need complete 316 unique HTTP capture")
    strict = a.profile.endswith("strict-10s")
    if strict:
        if not all(row.get("deadline_status") in
                   ("on_time", "http_error", "timeout", "late_response", "transport_error")
                   for row in rows):
            raise ValueError("strict profile requires actual deadline results")
        if any(row["http_status"] == 200 and row["elapsed_ms"] > 10000 for row in rows):
            raise ValueError("late success violates strict deadline")
    if a.profile == "projected-10s" and not all(
            row.get("deadline_projection") in ("late_as_error", "on_time")
            for row in rows):
        raise ValueError("projected profile requires explicit late-as-error rows")
    if a.mode == "organizer":
        organizer = [row for row in rows if row["dataset"] == "organizer"]
        if len(organizer) != 103:
            raise ValueError("need all 103 organizer requests")
        with a.out.open("w") as stream:
            for row in organizer:
                if row["http_status"] == 200:
                    result = {**row["result"]["prediction"],
                              "ranked_slugs": row["result"]["ranked_slugs"]}
                else:
                    result = {}
                stream.write(json.dumps({"case_id": row["case_id"],
                                         "query_sha256": row["query_sha256"],
                                         "http_status": row["http_status"],
                                         "result": result,
                                         "elapsed_ms": row["elapsed_ms"]},
                                        ensure_ascii=False) + "\n")
        print(json.dumps({"file": str(a.out), "rows": len(organizer)}))
        return

    if not a.suite or not a.submission_id:
        raise ValueError("frozen export requires suite and submission ID")
    suite = json.loads(a.suite.read_text())
    cases = [case for case in suite["cases"] if case["tracks"] == [a.mode]]
    output = []
    for case in cases:
        row = by_id[case["case_id"]]
        if row["query_sha256"] != case["image_sha256"]:
            raise ValueError("query SHA mismatch " + case["case_id"])
        status = ("ok" if row["http_status"] == 200 else
                  "timeout" if row.get("deadline_status") in ("timeout", "late_response")
                  or row.get("deadline_projection") == "late_as_error" else "error")
        item = {"case_id": case["case_id"], "status": status,
                "latency_ms": round(row["elapsed_ms"])}
        if item["status"] == "ok":
            item["prediction"] = row["result"]["prediction"]
        output.append(item)
    digest = hashlib.sha256()
    server_file = ("server_rich.py" if a.profile == "rich-uncapped" else
                   "server_website.py" if a.profile.startswith("website-") else
                   "server.py")
    files = [server_file,
             ("run_suite_curl.py" if strict else "run_suite.py"),
             "export.py"]
    if a.profile == "projected-10s":
        files.append("project_deadline.py")
    for name in files:
        digest.update((Path(__file__).parent / name).read_bytes())
    if strict and not a.runtime_receipt:
        raise ValueError("strict profile requires exact runtime receipt")
    if a.runtime_receipt:
        receipt = json.loads(a.runtime_receipt.read_text())
        if receipt.get("profile") != a.profile:
            raise ValueError("runtime receipt profile mismatch")
        digest.update(json.dumps(receipt, sort_keys=True,
                                 ensure_ascii=False).encode())
    names = {
        "uncapped": "Fresh B → Qwen3-VL-Reranker-2B Top20 (uncapped HTTP diagnostic)",
        "projected-10s": "Fresh B → Qwen3-VL-Reranker-2B Top20 (retrospective 10s projection)",
        "strict-10s": "Fresh B → Qwen3-VL-Reranker-2B Top20 (strict 10s HTTP)",
        "rich-uncapped": "Fresh B → Qwen3-VL-Reranker-2B Top20 + catalog filename (uncapped HTTP)",
        "website-uncapped": "Fresh B → Qwen3-VL-Reranker-2B Top20 + public website metadata (uncapped HTTP)",
        "omp1-strict-10s": "Fresh B (OMP1) → Qwen3-VL-Reranker-2B Top20 (strict 10s HTTP)",
        "website-strict-10s": "Fresh B → Qwen3-VL-Reranker-2B Top20 + public website metadata (strict 10s HTTP)",
        "website-omp1-strict-10s": "Fresh B (OMP1) → Qwen3-VL-Reranker-2B Top20 + public website metadata (strict 10s HTTP)",
    }
    payload = {
        "submission_id": a.submission_id,
        "suite_version": suite["version"], "suite_hash": suite["suite_hash"],
        "track": a.mode,
        "basket_ids": sorted(b["basket_id"] for b in suite["baskets"]
                             if b["track"] == a.mode),
        "solution": {
            "name": names[a.profile],
            "version": "qwen3vl-reranker2b-top20-fresh-http-" + a.profile,
            "commit": None, "config_hash": digest.hexdigest()[:16],
            "weights_version": "Qwen/Qwen3-VL-Reranker-2B@4bd860ac4f15ad1897a214615cccc700f8f71818",
            "catalog_version": suite["catalog_sha256"][:16],
        },
        "submitted_by": "night-qwen-fresh-http-gold-blind",
        "results": output,
    }
    a.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"file": str(a.out), "rows": len(output),
                      "errors": sum(item["status"] != "ok" for item in output)}))


if __name__ == "__main__":
    main()
