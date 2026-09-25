"""Adapt saved reader results to the trusted unique-organizer scorer."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ranked", type=Path, required=True)
    p.add_argument("--variant", choices=("reader_ocr", "reader_fused"), required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.ranked.read_text().splitlines() if line]
    rows = [r for r in rows if r["dataset"] == "organizer"]
    if len(rows) != 103:
        raise ValueError("need 103 organizer files")
    with a.out.open("w") as stream:
        for r in rows:
            prediction = r[a.variant + "_prediction"]
            ranked = r[a.variant + "_top20"]
            result = {**prediction, "ranked_slugs": [x["slug"] for x in ranked]}
            stream.write(json.dumps({"case_id": r["case_id"],
                                     "query_sha256": r["query_sha256"],
                                     "http_status": 200, "result": result,
                                     "elapsed_ms": r["reader_elapsed_ms"]},
                                    ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(a.out), "rows": len(rows), "variant": a.variant}))


if __name__ == "__main__":
    main()
