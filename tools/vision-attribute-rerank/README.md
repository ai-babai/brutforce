# Offline attribute rerank diagnostic

This tool reorders **existing Top-20 candidates only**. It reads saved OCR and
catalog metadata; it does not call models, APIs, or GPUs. `RULES-v1.md` is the
fixed rule contract and was written before scoring against private answers.

Architecture:

1. `rerank.py` loads display-v2 and the official CSV, setting conflicting or
   unknown color/sweetness/year fields to neutral.
2. It parses explicit OCR attributes and finds existing same-producer,
   same-title candidate groups backed by sufficient title evidence.
3. It stably reorders only those group members in their original Top-20 slots,
   emitting reasons and old/new candidate lists. Error, no-match, and
   non-wine OCR rows are unchanged.
4. `score.py` reads the frozen gold and organizer seal **after** the rerank
   outputs are written and hashed. It applies the separate frozen erratum as
   an overlay in memory. Case-level score changes go to a private file;
   aggregate counts go to a public-safe file.

Run `python3 -m unittest discover -s tools/vision-attribute-rerank -p 'test_*.py'`.
The reproducible input paths, SHA-256 values, CPU reorder measurements, and
output paths are pinned in the gold-blind manifest under the private
`attribute-rerank/gold-blind-v1/` experiment directory.

This is **post-hoc development** on reviewed photos. A measured improvement
here is not an independent validation result or a full HTTP latency claim.
The catalog lacks reliable vintage metadata for some same-name variants, so
those cannot be fixed by a safe vintage rule.

## Reproduce locally

Run from the repository root. BRUT_DATA_ROOT points to exported local data;
these Mac paths are not server paths. The input names below map directly to
the 12 entries in the pinned manifest. Use a fresh output directory if
repeating the run.

    BRUT_DATA_ROOT=/Users/skif/ml-data/brutforce
    EXP_ROOT=$BRUT_DATA_ROOT/vision-retrieval-20260925/attribute-rerank
    python3 tools/vision-attribute-rerank/rerank.py \
      --display "$BRUT_DATA_ROOT/vision-retrieval-20260925/catalog-audit/display-wines-20260922-v2.jsonl" \
      --official-csv "$BRUT_DATA_ROOT/materials/2026-09-19-organizers/dataset/strapi_output0709.csv" \
      --out-dir "$EXP_ROOT/gold-blind-v1" \
      --input "frozen-paddle=$BRUT_DATA_ROOT/vision-baselines-20260924/paddle.jsonl" \
      --input "frozen-deepseek=$BRUT_DATA_ROOT/vision-baselines-20260924/deepseek-prompt-v1.jsonl" \
      --input "frozen-qwen=$BRUT_DATA_ROOT/vision-baselines-20260924/qwen-prompt-v1.jsonl" \
      --input "frozen-owlv2=$BRUT_DATA_ROOT/vision-retrieval-20260924/eval-v2-label-context/fused.jsonl" \
      --input "frozen-yoloe=$BRUT_DATA_ROOT/vision-retrieval-20260925/detectors/yoloe26s/full-eval.jsonl" \
      --input "frozen-rtdetr=$BRUT_DATA_ROOT/vision-retrieval-20260925/detectors/rtdetr-r18/full-eval.jsonl" \
      --input "organizer-paddle=$BRUT_DATA_ROOT/vision-retrieval-20260924/organizer-audit/paddle-standalone.jsonl" \
      --input "organizer-deepseek=$BRUT_DATA_ROOT/vision-retrieval-20260924/organizer-audit/deepseek-standalone.jsonl" \
      --input "organizer-qwen=$BRUT_DATA_ROOT/vision-retrieval-20260924/organizer-audit/qwen-standalone.jsonl" \
      --input "organizer-owlv2=$BRUT_DATA_ROOT/vision-retrieval-20260924/organizer-v2-label-context/fused.jsonl" \
      --input "organizer-yoloe=$BRUT_DATA_ROOT/vision-retrieval-20260925/detectors/yoloe26s/full-organizer.jsonl" \
      --input "organizer-rtdetr=$BRUT_DATA_ROOT/vision-retrieval-20260925/detectors/rtdetr-r18/full-organizer.jsonl"

Only after the gold-blind manifest exists, run the separate scorer:

    python3 tools/vision-attribute-rerank/score.py \
      --gold-blind-dir "$EXP_ROOT/gold-blind-v1" \
      --frozen-suite "$BRUT_DATA_ROOT/eval-v1/baskets/v1.json" \
      --frozen-gold "$BRUT_DATA_ROOT/eval-v1/private/gold-v1.json" \
      --frozen-erratum "$BRUT_DATA_ROOT/vision-retrieval-20260925/annotation/frozen-v1-errata.json" \
      --organizer-manifest "$BRUT_DATA_ROOT/vision-retrieval-20260924/organizer-audit/queries-public.json" \
      --organizer-seal "$BRUT_DATA_ROOT/vision-retrieval-20260925/annotation/sealed-v1.jsonl" \
      --private-out "$EXP_ROOT/private-score-v3.json" \
      --public-out "$EXP_ROOT/public-summary-v3.json"

The scoring step verifies each saved prediction against the frozen suite or
organizer query image SHA (standalone frozen records carry the suite hash),
checks transport status (HTTP 200 or 201), and scores service and retrieval separately.
The v3 public and private outputs pin this scorer file SHA-256 and suite/manifest versions.
