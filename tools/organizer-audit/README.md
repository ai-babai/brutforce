# Organizer query audit

The source images, model responses, ledgers, and labels live outside Git in
`/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit`.
Set `BRUTFORCE_AUDIT_ROOT` to use another data root, such as the copy on Sigma.
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
- `benchmark_pipeline.py`: public-only, SHA-checked HTTP timing client. It
  separates the first request after service readiness from warm requests.
- `score_composition.py`: reviewer-side aggregate for the seven fused
  retrieval variants. It reads private local labels only after predictions
  are frozen; never copy labels to an inference host.

## Reproducing on Sigma

The public images and manifests are at
`/srv/lct/data/vision-retrieval/20260924/organizer-audit`. The organizer
manifest (`queries-server.json`) contains absolute Sigma image paths. The
synthetic manifest is `synthetic-server.json`. The script and frozen v1 matcher
sources are installed alongside the data under `code/organizer-audit` and
`code/vision-baselines`; the public CSV and allowed slugs are under
`public-catalog`. Use the existing Paddle environment for OCR. For example:

```sh
export BRUTFORCE_AUDIT_ROOT=/srv/lct/data/vision-retrieval/20260924/organizer-audit
export BRUTFORCE_EVAL_ROOT="$BRUTFORCE_AUDIT_ROOT/public-catalog"
export BRUTFORCE_CATALOG_CSV="$BRUTFORCE_EVAL_ROOT/strapi_output0709.csv"
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
cd "$BRUTFORCE_AUDIT_ROOT/code"
/srv/lct/maks/vision-baselines/venv/bin/python organizer-audit/paddle_remote.py \
  --manifest "$BRUTFORCE_AUDIT_ROOT/queries-server.json" \
  --out "$BRUTFORCE_AUDIT_ROOT/paddle-ocr.jsonl"
/srv/lct/maks/vision-baselines/venv/bin/python organizer-audit/postprocess_paddle.py \
  --input "$BRUTFORCE_AUDIT_ROOT/paddle-ocr.jsonl" \
  --output "$BRUTFORCE_AUDIT_ROOT/paddle-standalone.jsonl"
```

The standalone DeepSeek/Qwen runner uses the same public CSV and allowed
slugs. Set `BRUTFORCE_OPENROUTER_KEY_FILE` to a readable secret-file path and
run, for example, `python organizer-audit/run_standalone.py --model deepseek
--manifest "$BRUTFORCE_AUDIT_ROOT/queries-server.json"`. The runner writes an
attempt ledger and enforces a combined USD cap. Existing results are complete;
do not repeat paid calls to reproduce the report. For local postprocessing,
`BRUTFORCE_BASELINE_ROOT` points to frozen v1 baseline JSONL files and
`BRUTFORCE_PILOT_ROOT` points to prior synthetic pilot metadata.

Keep private `labels-private.json` and `synthetic-private-targets.json` away
from inference hosts. `analyze.py` needs these only after predictions are
frozen; unlabeled organizer images have no accuracy denominator.

## HTTP timing

Use the same `benchmark-queries.json` and original image bytes on each host.
The client verifies every input SHA and the SHA echoed by the endpoint, calls
`/healthz` to record model load time, then sends one sequential loopback HTTP
request per image. The first request is separate. Warm p50/p95/max include
distinct later images; `full_pipeline_warm_*` further requires OCR to have
executed without error. It is a sequential local latency check, not a network
or concurrent-load benchmark. Example (after starting `server.py`):

```sh
python organizer-audit/benchmark_pipeline.py \
  --manifest "$BRUTFORCE_AUDIT_ROOT/benchmark-queries.json" \
  --image-root "$BRUTFORCE_AUDIT_ROOT" \
  --url http://127.0.0.1:8080/v1/eval/predict \
  --hardware-label rtx4090 --device cuda --cpu-threads 2 --omp-threads 1 \
  --out "$BRUTFORCE_AUDIT_ROOT/benchmark-rtx4090.json" --limit 24
```

The frozen v1 suite, gold, and baseline code were not changed. See
`ERROR-REPORT.ru.md` in the data directory for measured counts, provenance,
error categories, and limitations.

## Later locally reviewed real-photo annotations

`score_reviewed.py` scores a separate versioned annotation JSONL against frozen
standalone or composition predictions. It validates image hashes and separates
exact identification from ambiguous, insufficient and unresolved catalog cases.
Missing/error predictions remain in the exact-label denominator. The public
aggregate contains no case answers; the required `--private-out` trace does.
Do not use provisional contact-sheet guesses as ground truth. `out_of_catalog`
requires documented catalog inspection, not a failed literal name search.

```sh
python score_reviewed.py --labels "$REVIEWED_JSONL" --predictions "$FROZEN_JSONL" \
  --variant all --out "$PUBLIC_AGGREGATE" --private-out "$PRIVATE_TRACE"
python -m unittest discover -s tools/organizer-audit -p test_score_reviewed.py
```

Omit `--variant` for standalone outputs. Their recorded wall duration and full
HTTP `elapsed_ms` support deadline-aware scoring. For live HTTP, only `--variant
all` is the actual returned response; other branches are diagnostic rankings,
with no returned-response accuracy or deadline score. Cached composition stage
sums are not live HTTP latency. These are local agent-reviewed labels, not an organizer answer
key. Publish annotation coverage and prior-seen split alongside accuracy.

Before scoring a new review, use `merge_reviews.py --queries PUBLIC_QUERIES
--suite FROZEN_SUITE --catalog PUBLIC_CATALOG --review FIRST_REVIEW
--review SECOND_REVIEW --out VERSIONED_PRIVATE_JSONL --summary PRIVATE_AUDIT_JSON`.
This requires all unique photos, validates identities and catalog membership,
rebuilds prior-seen groups from image hashes, and refuses to overwrite outputs.
`compare_reviewed.py` can then compare frozen prediction files listed in a JSON
array (`name`, `path`, optional `variants`). Its public aggregates include coverage,
ranking errors, and an equal-weight average over confirmed catalog wine IDs.
Repeated scenes remain recorded separately, not an independent new wine per photograph.
Catalog aliases and title/photo conflicts require explicit review; visual similarity
to a reference alone is not proof of a unique organizer slug.

## Reference quarantine gate

`reference_gate.py --catalog EXACT_INDEX_MANIFEST --index OLD_INDEX
--decisions VERSIONED_DECISIONS --out NEW_INDEX` copies the index and disables
only exact slug/image-SHA pairs supported by evidence. It verifies the original
manifest digest and slug order, refuses existing output directories, preserves
all text-catalog entries, and records index/decision hashes. Four tests cover
isolation, replaced-image mismatch, order mismatch and missing evidence.

The September25 gate excludes17 previously quarantined images accidentally
restored through archive fallback plus2 newly confirmed mismatches. It leaves
2061 visual references and42 unavailable slots out of2103; this is not full
semantic certification of every remaining photo. Old experiment files and scores
remain immutable; only separately named reruns use the gated index.
