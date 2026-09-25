"""Check fresh B action and Top20 parity after an output-preserving runtime change."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    inputs = {r["case_id"]: r for r in map(json.loads, a.inputs.read_text().splitlines())}
    baseline = {r["case_id"]: r["result"]["b_result"] for r in
                map(json.loads, a.baseline.read_text().splitlines())}
    ids = ["case-000001", "case-000015", "case-000042", "case-000046",
           "case-000070", "case-000105", "case-000146", "case-000200",
           "organizer-real-001", "organizer-real-055"]
    rows = []
    for case_id in ids:
        row = inputs[case_id]
        req = Request(a.url + "/v1/eval/predict?track=" + row["track"],
                      data=(a.queries / row["query_path"]).read_bytes(),
                      headers={"Content-Type": "application/octet-stream"})
        with urlopen(req, timeout=45) as response:
            result = json.load(response)
        old = baseline[case_id]
        item = {"case_id": case_id,
                "sha_equal": result["image_sha256"] == old["image_sha256"],
                "action_equal": result.get("action") == old.get("action"),
                "top20_equal": result["ranked_slugs"] == old["ranked_slugs"],
                "top20_set_equal": set(result["ranked_slugs"]) == set(old["ranked_slugs"]),
                "b_total_ms": result["timings_ms"]["total_ms"],
                "b_ocr_ms": result["timings_ms"].get("ocr_ms")}
        rows.append(item)
        print(json.dumps(item), flush=True)
    a.out.write_text("\n".join(map(json.dumps, rows)) + "\n")
    assert all(r["sha_equal"] and r["action_equal"] and
               r["top20_equal"] for r in rows)


if __name__ == "__main__":
    main()
