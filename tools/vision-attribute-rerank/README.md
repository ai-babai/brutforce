# Offline attribute rerank diagnostic

This tool reorders **existing Top-20 candidates only**. It reads saved OCR and
catalog metadata; it does not call models, APIs, or GPUs. \`RULES-v1.md\` is the
fixed rule contract and was written before scoring against private answers.

Architecture:

1. \`rerank.py\` loads display-v2 and the official CSV, setting conflicting or
   unknown color/sweetness/year fields to neutral.
2. It parses explicit OCR attributes and finds existing same-producer,
   same-title candidate groups backed by sufficient title evidence.
3. It stably reorders only those group members in their original Top-20 slots,
   emitting reasons and old/new candidate lists. Error, no-match, and
   non-wine OCR rows are unchanged.
4. \`score.py\` reads the frozen gold and organizer seal **after** the rerank
   outputs are written and hashed. It applies the separate frozen erratum as
   an overlay in memory. Case-level score changes go to a private file;
   aggregate counts go to a public-safe file.

Run \`python3 -m unittest discover -s tools/vision-attribute-rerank -p 'test_*.py'\`.
The reproducible input paths, SHA-256 values, CPU reorder measurements, and
output paths are pinned in the gold-blind manifest under the private
\`attribute-rerank/gold-blind-v1/\` experiment directory.

This is **post-hoc development** on reviewed photos. A measured improvement
here is not an independent validation result or a full HTTP latency claim.
The catalog lacks reliable vintage metadata for some same-name variants, so
those cannot be fixed by a safe vintage rule.
