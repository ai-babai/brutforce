"""Submit saved reader rankings with reader-only measured latency."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--ranked", type=Path, required=True)
    p.add_argument("--variant", choices=("reader_ocr", "reader_fused"), required=True)
    p.add_argument("--track", choices=("service", "retrieval"), required=True)
    p.add_argument("--submission-id", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    suite = json.loads(a.suite.read_text())
    ranked = [json.loads(line) for line in a.ranked.read_text().splitlines() if line]
    by_id = {r["case_id"]: r for r in ranked}
    if len(ranked) != 316 or len(by_id) != 316:
        raise ValueError("ranked file must contain 316 unique IDs")
    cases = [c for c in suite["cases"] if c["tracks"] == [a.track]]
    out = []
    for c in cases:
        r = by_id[c["case_id"]]
        if r["query_sha256"] != c["image_sha256"]:
            raise ValueError("query SHA mismatch: " + c["case_id"])
        prediction = r[a.variant + "_prediction"]
        status = "ok" if a.track == "service" or prediction.get("ranked_slugs") else "error"
        item = {"case_id": c["case_id"], "status": status,
                "latency_ms": round(r["reader_elapsed_ms"])}
        if status == "ok":
            item["prediction"] = prediction
        out.append(item)
    digest = hashlib.sha256()
    for name in ("read.py", "rank.py", "export_eval.py"):
        digest.update((Path(__file__).parent / name).read_bytes())
    payload = {
        "submission_id": a.submission_id, "suite_version": suite["version"],
        "suite_hash": suite["suite_hash"], "track": a.track,
        "basket_ids": sorted(b["basket_id"] for b in suite["baskets"] if b["track"] == a.track),
        "solution": {"name": "Cached B → Qwen3-VL-2B reader " + a.variant + " (reader timing only)",
                     "version": "qwen3vl2b-target-transcription-v1", "commit": None,
                     "config_hash": digest.hexdigest()[:16],
                     "weights_version": "Qwen/Qwen3-VL-2B-Instruct@89644892e4d85e24eaac8bacfd4f463576704203",
                     "catalog_version": suite["catalog_sha256"][:16]},
        "submitted_by": "night-reader-gold-blind", "results": out,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"file": str(a.out), "rows": len(out),
                      "errors": sum(r["status"] == "error" for r in out),
                      "latency_note": "reader-only measured; excludes cached B and HTTP"}))


if __name__ == "__main__":
    main()
