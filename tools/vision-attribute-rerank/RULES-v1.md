# Attribute rerank v1 — frozen rule specification

Status: **post-hoc development diagnostic**, written before running this rule on gold.
It uses saved OCR/transcription and saved Top-20 candidates only. No model inference,
weights, catalog search, or candidate insertion is allowed. The original prediction
files and gold remain unchanged.

## Catalog evidence

Read display-v2 (2,038 records) and the official organizer CSV (2,103 unique slugs).
For a slug, use color only when the display category and every CSV row agree on
`белое`, `красное`, or `розовое`. Use sweetness only when display `sweetness` and
display `category_and_sweetness` agree. Conflicting or missing fields are unknown.
For a CSV-only slug, color may be used if all CSV rows agree; sweetness is unknown.
Use a vintage only when the same single four-digit year occurs explicitly in both
display and CSV **title** fields. A slug suffix, image, or reviewer answer is not
vintage metadata. No structured vintage field exists for the Aratti 2023/2024 pair,
so the rule must abstain on year there.

## OCR evidence

Use only the source's target OCR `raw_text` or `ocr_text`. Parse explicit whole-word
Russian color and sweetness terms and one 19xx/20xx vintage. Do not infer color from
grape names, bottle color, producer, or “по-белому”. Treat multiple distinct values
for an attribute as ambiguous. Parse `полусухое` separately from `сухое`, and
`полусладкое` separately from `сладкое`. Reject `сухофрукты`, `полусухарики`, and
other non-wine word substrings. A non-wine OCR action yields no attributes.

## Safe reorder

Keep status errors, `no_match`, `insufficient_information`, empty candidates, and
non-wine OCR actions unchanged. Only consider a group of at least two existing
Top-20 candidates with the **same producer and normalized title** (year removed
from the title for grouping). The OCR must contain at least two distinctive title
tokens (length ≥5) or one such title token plus one distinctive producer token.
Generic words such as wine, white, red, dry, winery, and sparkling do not count.
Do not tie candidates from different producers. Unknown/conflicting catalog fields
score zero. For each explicit OCR attribute, add +1 for a known match and -1 for
a known mismatch. Rerank *within the group's original positions* by descending
attribute score, stable on ties. Do not move a candidate across other groups or
change the candidate set. Require at least one group's score spread; otherwise
preserve the list exactly. Record the input attributes, group, scores, and reason.

For service rows with a matching action/slug, set the diagnostic slug to the new
Top-1 only if the original Top-1 belongs to a reordered group. For retrieval rows,
reorder the saved list but do not synthesize a service action. Latency is an offline
CPU reorder measurement only, never a full HTTP time.

## Evaluation boundary

Write all diagnostic outputs first and hash them. Then read private frozen gold
and the sealed organizer subset to score saved baseline versus rerank. Correct the
known frozen case-000137 lineage only through the separate versioned erratum;
do not rewrite historical reports. Report all 213 frozen cases and all organizer
cases with available saved OCR/Top-20, with exact denominators and unchanged
no-match/error counts. Case-level changes stay private. Public tables have only
aggregate deltas. Because these rules were motivated by reviewed failures, any
apparent gain is **post-hoc development** and not independent validation.
