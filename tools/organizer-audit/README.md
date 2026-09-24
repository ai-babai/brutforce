# Organizer query audit

The source images, model responses, ledgers, and labels live outside Git in
`/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit`.
The public manifests contain case IDs, image paths, SHA-256 and catalog refs;
`labels-private.json` and `synthetic-private-targets.json` are read only by
`analyze.py`, after predictions are frozen. They never enter the OCR runner,
Paddle process, or catalog matcher.

- `run_standalone.py`: existing DeepSeek/Qwen v1 prompt and unchanged public
  catalog matcher on original organizer or prior synthetic images. Records
  every paid attempt, including timeouts, and enforces an API budget cap.
- `paddle_remote.py`: Sigma-only PaddleOCR CPU, two threads, geometric center
  crop; records OCR without catalog or labels.
- `postprocess_paddle.py`: applies the same v1 catalog matcher to Paddle text.
- `build_effective.py`: selects frozen-v1 results for 12 exact-SHA repeated
  real photos, fresh results for 88, and SHA aliases for the three public-eval
  duplicates. Fresh full repeats remain separately archived.
- `derive_v2.py`: existing cached cultivar rerank, development only.
- `analyze.py`: produces aggregate JSON and private case-level traces using
  agent-verified local matches and synthetic pilot metadata.

The frozen v1 suite, gold, and baseline code were not changed. See
`ERROR-REPORT.ru.md` in the data directory for measured counts, provenance,
error categories, and limitations.
