# Standalone OCR baselines

`run.py` tests one vision OCR model at a time on frozen public LCT images.
DeepSeek and Qwen receive the same image and prompt by track. Both use the
same fixed `matcher.py` over the 2103 public organizer catalog records. The
method is **vision OCR + lexical retrieval**, not an end-to-end model.

Dependencies: Python 3 and Pillow. Data and results stay outside Git.

```sh
python run.py --model deepseek --case-id case-000072 --case-id case-000098 \
  --case-id case-000073 --case-id case-000099
python run.py --model qwen --case-id case-000072 --case-id case-000098 \
  --case-id case-000073 --case-id case-000099
```

The runner verifies the sealed image SHA-256, omits already attempted cases,
records each API attempt and usage, enforces cost reserves, and writes private
JSONL diagnostics under `vision-baselines-20260924`. Its current 8-second
`urllib` timeout applies to individual blocking socket operations and is not
an end-to-end deadline. Both API latency and total local processing latency
are recorded. The exporter marks any prediction whose total elapsed time
exceeds the 10-second contest deadline as `timeout`; a separate audit lists
these changes. Responses are not retried.

For service, the prompt asks the vision model to choose the target wine before
reading text and to avoid a more legible neighbor. For retrieval, the image is
a verified crop. The fixed matcher ranks public catalog slugs. The service
policy maps non-wine/no-wine to `no_match`, unreadable to
`insufficient_information`, and a matched wine to a slug. These actions are
diagnostic product extensions; the organizer endpoint accepts a slug only.

Results must be scored using the existing eval service or local scorer, with
gold kept outside this process. Report by basket, origin kind, scene group,
timeouts, latency, and observed API cost. Do not interpret derived variants
as 213 independent wines.

## PaddleOCR CPU baseline

`paddle_remote.py` runs only on Sigma in
`/srv/lct/maks/vision-baselines/venv` against its copy of the same sealed
suite. It uses PaddleOCR 3.7.0, PaddlePaddle 3.3.0 CPU, PP-OCRv5 mobile
detection, and the East Slavic mobile recognition model with two CPU inference
threads. It disables oneDNN
because PaddlePaddle 3.3.0 CPU inference raises an unsupported PIR attribute
error on this environment ([upstream issue](https://github.com/PaddlePaddle/Paddle/issues/77340)). It limits detection to 1280 pixels on the long
side and records raw OCR lines, scores, and boxes. The service image is first
cropped to the central 60% of width and 84% of height; this is a fixed
geometric target heuristic, with no semantic wine selection. Retrieval uses
the full verified label crop. Any result over 8 seconds is marked timeout.

Copy `paddle-ocr.jsonl` from Sigma into the local result directory, then run
`postprocess_paddle.py`. It applies the same `matcher.py` used above and
produces `paddle.jsonl`. The producer/model fields remain empty because
PaddleOCR returns literal text, not structured wine attributes. This makes
the comparison transparent and gives the Paddle baseline a harder catalog
query than models that can extract fields.

`export_submission.py` makes one service and one retrieval submission JSON
per model. It reads recorded predictions only. Its output is private until
the evaluation service scores it.

## Offline development variants

After both API baselines have been scored independently,
`offline_variants.py` can derive three new 213-case files from their frozen
OCR and candidate lists without new model calls:

- DeepSeek OCR + matcher v2, and Qwen OCR + matcher v2: a generic catalog
  rerank that treats common Latin/Cyrillic grape spellings as equivalents.
- RRF60: rank fusion of the two v1 top-20 lists. Service uses a conservative
  `no_match` vote gate before selecting the fused top slug.

The RRF latency is the maximum of the two separately measured local totals,
which models parallel completion. It is **not** a live HTTP timing result.
All three variants were devised after seeing baseline scores on this same
suite; their scores are development findings, not independent validation.

## Frozen v1 results, 2026-09-24

Suite hash: `10b0e4bcb93d4a55c8f82ad8427eda3c777b8acd9adcc8ccd7d35c17cf041957`.
All 213 cases were attempted by each standalone method. Service has 141
graded and 10 ungraded cases; retrieval has 62 graded cases. These are
diagnostic baskets with many variants of a small number of source scenes.
Scores come from the eval participant reports retained with the raw outputs
outside Git.

| Method | Service top-1 | Retrieval top-1 | Retrieval top-5 | Retrieval top-20 | Median total service / retrieval |
|---|---:|---:|---:|---:|---:|
| DeepSeek OCR + matcher v1 | 98/141 | 39/62 | 54/62 | 58/62 | 2.55 / 2.82 s |
| Qwen OCR + matcher v1 | 101/141 | 43/62 | 57/62 | 57/62 | 2.47 / 2.82 s |
| PaddleOCR + center ROI + matcher v1 | 47/141 | 23/62 | 42/62 | 48/62 | 1.65 / 2.00 s |
| DeepSeek cached OCR + matcher v2 | 108/141 | 45/62 | 56/62 | 58/62 | Same cached inference |
| Qwen cached OCR + matcher v2 | 111/141 | 49/62 | 57/62 | 57/62 | Same cached inference |
| DeepSeek + Qwen cached RRF60 on v1 lists | 109/141 | 43/62 | 58/62 | 58/62 | Parallel simulation only |

DeepSeek v1 model calls cost `$0.044724274` and Qwen v1 calls cost
`$0.0875360882` by OpenRouter `usage.cost`. These exclude abandoned v0
smoke attempts and unknown billing on interrupted or timed-out calls. Paddle
ran on existing Sigma CPU capacity; no hosted GPU was used.

The most useful error split is semantic. DeepSeek matched only 2/10
non-wine lookalikes (IMG-14), often calling them wine before catalog search;
Qwen matched 10/10. Qwen matched only 6/10 no-bottle scenes (IMG-15), while
DeepSeek matched 9/10. Both failed 2/2 out-of-catalog wine scenes (IMG-19).
Paddle's fixed center ROI missed side wine (IMG-12: 1/10), and raw OCR cannot
reject non-wine or no-bottle scenes (IMG-14 and IMG-15: 0/10 each). Paddle
timed out on seven dense service frames at the 8-second internal threshold.

Matcher v2 adds generic Latin/Cyrillic grape spelling aliases. It corrected
the visible `CABERNET SAUVIGNON` vs `Каберне Совиньон` mismatch where v1
ranked a Riesling from the same producer first. **All** ten service and six
retrieval top-1 gains for each model are variants of one source scene;
there were no case-level losses on
this suite. This is a targeted regression fix, with independent scenes needed
to assess general benefit. RRF60 instead improves some no-bottle and
multi-wine service cases via its action gate, but adds no retrieval top-1
gain over Qwen v1. Paddle has no retrieval cases uniquely correct beyond
Qwen matcher v2, so no Paddle fusion variant was made.

API baseline timings include local image preparation, network inference,
and lexical matching. The OpenRouter socket timeout was not a hard total
deadline: exported submissions change any total over 10 seconds to
`timeout` and keep the raw OCR for diagnosis. No live contest HTTP endpoint
was timed; the RRF latency uses separately measured calls and must not be
used as deployment latency evidence.
