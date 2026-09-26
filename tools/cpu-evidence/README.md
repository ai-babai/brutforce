# CPU evidence · ML-083

## H2 field identity candidate (separate branch)

This branch replaces only the identity decision in `processor.py` with
`field_matcher.py`. The first pinned candidate at `4bcc925` remains untouched.
The selected target crop, overlap guard, single existing ORT6 backend, OCR
worker, response envelope and budget remain the same. OCR is attempted when
the unchanged visual Top20 contains at least two independently verified grape
fields; candidates need not share the visual Top1's producer or family.

For every Top20 candidate, the public card supplies `winery` as producer,
non-generic title tokens outside producer and variety as line, and a single
grape only when both `grapes` and `title` explicitly agree. OCR readings must
be literal, on the selected target, and score at least 0.75. Each of producer,
line and grape is used only if the matched catalog value is unambiguous among
the Top20. Missing catalog fields and absent or ambiguous OCR readings remain
unknown; explicit conflicts alone create a contradiction. A candidate needs
positive grape and producer/line evidence, and the visual winner must have an
explicit contradiction, before a stable categorical partition (supported,
unknown, contradicted) can change the order. This is not score fusion and never
introduces a SKU outside the original Top20. It never changes `no_match`, target
selection, or negative action.

Prediction, to be checked by paired HTTP and independent scoring: some errors
with correct identity at visual ranks 2–5 can become Top1 when OCR reads its
distinguishing fields on the selected bottle. H2 cannot repair identities
absent from Top20, failed target selection, unreadable/conflicting OCR, or
unknown catalog metadata. This is a hypothesis, not an accuracy estimate.

After H2 quality and timing are measured, a separate offline-only bounded
experience may inspect delayed wine-gate/target hypotheses on fixed public
images: replay existing RT-DETR/Base224/OWLv2 outputs, log rejected bottle
boxes and gate margins without changing action, and compare the rescued target
crop to known public visual references. That experiment requires its own plan;
it is not implemented in this branch or used on TEST during H2.

## Initial strict-family candidate (pinned at 4bcc925)

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
selected target box and crop hash, worker OCR time, hook elapsed time and explicit
errors. Only an OCR family/producer anchor at score ≥0.65 and a single candidate
grape at score ≥0.75 permit promotion; missing/ambiguous readings stay unknown.
The response also retains the original whole-view branch and image SHA. Never write OCR/photo
contents to common logs; raw HTTP rows are private evaluation artifacts.
OCR and catalog strings use the night experiment's mixed-script lookalike
normalization before transliteration; diagnostics preserve each literal line and
its confidence. The 8.5-second product budget leaves a 350 ms response reserve:
the OCR timeout is the minimum of the configured cap and remaining time. If the
remaining budget is too small, `budget_exhausted` leaves the visual order intact.

On Sigma, TEST already holds SO400M and lacks enough free memory for a second
ORT6 process. For the paired experiment the runtime owner runs the lightweight
`http_wrapper.py` on loopback 8127, forwarding each image to existing ORT6 on
8125, then asking the independent OCR worker on 8129 only when a same-family
variant is near the visual winner. No second encoder is loaded. The existing
backend must first expose `target_selection` (selected/competing boxes, original
whole Top20 with scores, selection reason) solely to loopback requests carrying
`X-ML083-Diagnostic: target-v1`. Normal response shape and rankings remain
unchanged; **coordinator reviews the diff before the runtime owner changes TEST**.

```sh
python tools/cpu-evidence/http_wrapper.py \
  --backend http://127.0.0.1:8125 --port 8127 \
  --catalog /srv/lct/data/vision-retrieval/20260925/detectors/catalog-audit/catalog-bundle.json \
  --cards /srv/lct/data/vision-retrieval/cpu-evidence-20260926/cards.json \
  --ocr-url http://127.0.0.1:8129 --ocr-timeout 3.0
```

After acceptance, the same matcher/OCR processor can run inside the existing
CPUPipeline without a forwarding hop. Its in-process hook also serves as a
reference for a machine with enough memory. Use the pinned ORT6 runtime
environment, `NIGHT_SO_ONNX_DIR`, and `PYTHONPATH` containing
`tools/vision-retrieval` and `tools/night-cpu`:

```sh
python tools/night-cpu/night_server.py \
  --encoder so400m --route onnx640 --threads 6 --port 8127 \
  --catalog /srv/lct/data/vision-retrieval/20260925/detectors/catalog-audit/catalog-bundle.json \
  --index-dir /srv/lct/data/vision-retrieval/20260925/detectors/so400m-gatev2/index \
  --evidence-cards /srv/lct/data/vision-service/benchmarks/ml-083/cards.json \
  --evidence-url http://127.0.0.1:8129 --evidence-timeout 3.0
```

The cards path is an example for the runtime owner to fill with a hash-verified
copy; its presence is required. Only the OCR worker needs an OCR package; the
matcher/wrapper uses existing PIL and stdlib. The in-process hook reuses the
ORT6 dependencies already loaded by CPUPipeline.

The inference process must not load gold. First compare paired full HTTP rows
on the pinned frozen 213 and organizer 103 inputs via the independent evaluator;
one development photo is diagnostic, not a quality estimate. Keep the ORT6
baseline, exact catalog/index and exclusion mask fixed. Existing night reports
showed no improvement for naive grape contradiction, sweetness rules, constant
CPU OCR or a permanent second visual crop; this check requires same-family
target evidence and skips unrelated queries instead.
