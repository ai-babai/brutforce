"""Convert saved gold-blind geometry output into v2 eval submissions."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--variant", choices=("local", "fusion", "cascade"), required=True)
    p.add_argument("--track", choices=("service", "retrieval"), required=True)
    p.add_argument("--submission-id", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    suite = json.loads(args.suite.read_text())
    rows = [json.loads(line) for line in args.raw.read_text().splitlines() if line]
    by_id = {r["case_id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate raw case IDs")
    cases = [c for c in suite["cases"] if c["tracks"] == [args.track]]
    output = []
    for case in cases:
        row = by_id[case["case_id"]]
        if row["query_sha256"] != case["image_sha256"]:
            raise ValueError("query SHA mismatch " + case["case_id"])
        rank = row[args.variant + "_top20"]
        if args.track == "retrieval":
            status = "ok" if rank else "error"
            prediction = {"ranked_slugs": rank}
        else:
            status = "ok"
            prediction = ({"slug": rank[0]} if rank else
                          {"action": row["baseline_action"] or "insufficient_information"})
        # Only this added stage was measured on the current GPU.
        latency = round(row["rerank_elapsed_ms"])
        entry = {"case_id": case["case_id"], "status": status, "latency_ms": latency}
        if status == "ok":
            entry["prediction"] = prediction
        output.append(entry)
    basket_ids = sorted(b["basket_id"] for b in suite["baskets"] if b["track"] == args.track)
    digest = hashlib.sha256()
    for name in ("run.py", "export_eval.py"):
        digest.update((Path(__file__).parent / name).read_bytes())
    payload = {
        "submission_id": args.submission_id,
        "suite_version": suite["version"], "suite_hash": suite["suite_hash"],
        "track": args.track, "basket_ids": basket_ids,
        "solution": {"name": "Cached B → DISK + LightGlue " + args.variant + " (rerank timing only)",
                     "version": "disk-depth-lightglue-fixed20-v1", "commit": None,
                     "config_hash": digest.hexdigest()[:16],
                     "weights_version": "B pinned + DISK depth + LightGlue disk_lightglue @ eb42fee2d71449efb0aa5c10549752b5d75384d8",
                     "catalog_version": suite["catalog_sha256"][:16]},
        "submitted_by": "night-lightglue-gold-blind",
        "results": output,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"submission": str(args.out), "results": len(output),
                      "errors": sum(r["status"] == "error" for r in output),
                      "latency_note": "measured offline rerank stage only; excludes B and HTTP"}))


if __name__ == "__main__":
    main()
