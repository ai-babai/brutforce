"""Gold-blind fresh HTTP driver; sends only original image bytes and track."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = [json.loads(line) for line in args.inputs.read_text().splitlines() if line]
    if len(manifest) != 316:
        raise ValueError("expected 316 input rows")
    existing = ([json.loads(line) for line in args.out.read_text().splitlines() if line]
                if args.out.exists() else [])
    done = {row["case_id"] for row in existing}
    if len(done) != len(existing):
        raise ValueError("duplicate existing rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a") as stream:
        for index, row in enumerate(manifest, 1):
            if row["case_id"] in done:
                continue
            body = (args.queries / row["query_path"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != row["query_sha256"]:
                raise ValueError("input SHA mismatch " + row["case_id"])
            request = urllib.request.Request(
                args.url + "/v1/eval/predict?track=" + row["track"],
                data=body, headers={"Content-Type": "application/octet-stream"})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    result = json.load(response)
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
                result = json.loads(exc.read().decode())
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            output = {"case_id": row["case_id"], "track": row["track"],
                      "dataset": row["dataset"], "query_sha256": row["query_sha256"],
                      "http_status": status, "elapsed_ms": elapsed, "result": result}
            stream.write(json.dumps(output, ensure_ascii=False) + "\n")
            stream.flush()
            if index % 10 == 0 or status != 200:
                print(json.dumps({"processed": index, "total": len(manifest),
                                  "case_id": row["case_id"], "http_status": status,
                                  "elapsed_ms": elapsed}), flush=True)
    print(json.dumps({"complete": True, "rows": len(manifest)}), flush=True)


if __name__ == "__main__":
    main()
