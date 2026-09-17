from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a safe schema and row-count profile for a Parquet file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.input.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    connection = duckdb.connect()
    schema_rows = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(source)]).fetchall()
    row_count = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(source)]).fetchone()[0]
    sample_rows = connection.execute("SELECT * FROM read_parquet(?) LIMIT 3", [str(source)]).fetchall()
    columns = [row[0] for row in schema_rows]
    profile = {
        "source_file": source.name,
        "bytes": source.stat().st_size,
        "row_count": row_count,
        "schema": [
            {"name": row[0], "type": row[1], "nullable": row[2], "key": row[3]}
            for row in schema_rows
        ],
        "sample": [dict(zip(columns, row)) for row in sample_rows],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"PASS: {row_count} rows, {len(columns)} columns", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
