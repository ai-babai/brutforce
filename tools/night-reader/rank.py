"""Gold-blind catalog-wide reader OCR search and unchanged B fusion."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reader", type=Path, required=True)
    p.add_argument("--baseline-eval", type=Path, required=True)
    p.add_argument("--baseline-organizer", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--vision-code", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    sys.path.insert(0, str(args.vision_code))
    from ranking import Lexical
    from fuse import ocr_top, rank_fuse

    refs = json.loads(args.catalog.read_text())["references"]
    slugs = [r["slug"] for r in refs]
    lexical = Lexical([{"slug": r["slug"], "title": r.get("title", ""),
                        "producer": r.get("winery", "")} for r in refs])
    baseline = rows(args.baseline_eval) + rows(args.baseline_organizer)
    by_id = {r["case_id"]: r for r in baseline}
    reader = rows(args.reader)
    if len(baseline) != 316 or len(by_id) != 316 or len(reader) != 316:
        raise ValueError("need 316 unique B and reader rows")
    if len({r["case_id"] for r in reader}) != 316:
        raise ValueError("duplicate reader case ID")
    mismatch = 0
    out = []
    for row in reader:
        b = by_id[row["case_id"]]
        if row["query_sha256"] != b["query_sha256"] or row["track"] != b["track"]:
            raise ValueError("B/reader input mismatch: " + row["case_id"])
        base = b["result"]
        transcription = row["text"] if row["status"] == "ok" else ""
        if transcription.strip().upper() == "<EMPTY>":
            transcription = ""
        reader_ocr = ocr_top(lexical, transcription, slugs)
        paddle_rebuilt = ocr_top(lexical, base.get("ocr_text", ""), slugs)
        paddle_served = base["branches_top20"]["ocr"]
        if [r["slug"] for r in paddle_rebuilt] != [r["slug"] for r in paddle_served]:
            mismatch += 1
        branches = {"whole": base["branches_top20"]["whole"],
                    "label": base["branches_top20"]["label"], "ocr": reader_ocr}
        fused = rank_fuse(branches)
        selected = (base.get("selection") or {}).get("selected_box") is not None
        def prediction(rank):
            if row["track"] == "service":
                return ({"action": "no_match"} if not selected else
                        {"slug": rank[0]["slug"]} if rank else
                        {"action": "insufficient_information"})
            return {"ranked_slugs": [x["slug"] for x in rank]}
        out.append({"case_id": row["case_id"], "track": row["track"],
                    "dataset": row["dataset"], "query_sha256": row["query_sha256"],
                    "reader_status": row["status"], "reader_text": row["text"],
                    "reader_elapsed_ms": row["elapsed_ms"],
                    "paddle_text": base.get("ocr_text", ""),
                    "paddle_ocr_top20": paddle_served,
                    "reader_ocr_top20": reader_ocr,
                    "baseline_top20": base.get("ranked_slugs", []),
                    "reader_fused_top20": fused,
                    "reader_ocr_prediction": prediction(reader_ocr),
                    "reader_fused_prediction": prediction(fused),
                    "baseline_prediction": {k: base[k] for k in ("slug", "action") if k in base},
                    "reader_model": row["model"], "reader_revision": row["revision"],
                    "reader_prompt_sha256": row["prompt_sha256"]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    changed = sum((r["baseline_top20"][0] if r["baseline_top20"] else None) !=
                  (r["reader_fused_top20"][0]["slug"] if r["reader_fused_top20"] else None)
                  for r in out)
    print(json.dumps({"rows": len(out), "paddle_reconstruction_mismatch": mismatch,
                      "reader_ocr_nonempty": sum(bool(r["reader_ocr_top20"]) for r in out),
                      "reader_fusion_changed_top1": changed}))


if __name__ == "__main__":
    main()
