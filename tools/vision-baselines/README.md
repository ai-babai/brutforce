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
