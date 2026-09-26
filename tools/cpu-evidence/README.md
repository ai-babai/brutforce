# CPU evidence · ML-083

Target-scoped, gold-blind identity check for the existing FP32 ORT6 whole-view
Top20. An optional hook in `tools/night-cpu/night_server.py` runs only when the
visual winner and another Top5 candidate have the same catalog producer and
distinctive title family (or both have grape-only titles with the same producer),
but different single grape fields independently present in title and catalog
grape metadata. The visual pool never changes. OCR must independently read
the title family or, for grape-only titles, the producer before any promotion.

The source of catalog fields is the pinned 2103-entry `cards.json` prepared
from the organizer/public catalog for the prior night experiment. Pass its
absolute path through `--evidence-cards`; do not pass private labels. For each
eligible target, the hook crops only the selected bottle or verified retrieval
image, sends a JPEG to `--evidence-url` (`POST /ocr`, raw JPEG), and expects
`{"texts": [...], "scores": [...], "ocr_ms": ...}`. The OCR worker runs in
its own process, without a second SO400M. OCR on an overlapping/ambiguous bottle
box, error, timeout, unreadable family/variant, or uncertain/blended catalog
field preserves the original visual order. No OCR text is guessed or substituted.

Diagnostic result: `evidence` includes before/after slug order, per-candidate
catalog field and observed/contradicts/unknown status, OCR literals and scores,
selected target box and crop hash, elapsed time and explicit errors. The response
also retains the original whole-view branch and image SHA. Never write OCR/photo
contents to common logs; raw HTTP rows are private evaluation artifacts.

The inference process must not load gold. First compare paired full HTTP rows
on the pinned frozen 213 and organizer 103 inputs via the independent evaluator;
one development photo is diagnostic, not a quality estimate. Keep the ORT6
baseline, exact catalog/index and exclusion mask fixed. Existing night reports
showed no improvement for naive grape contradiction, sweetness rules, constant
CPU OCR or a permanent second visual crop; this check requires same-family
target evidence and skips unrelated queries instead.
