# ML-086 R1: ORT6 target observations

`prepare.py` verifies public query SHA, joins unchanged ORT6 HTTP Top20 by
case ID/SHA/track, and takes the selected physical box from the independent
ORT6 metadata-only diagnostic. It refuses a different whole-branch Top20.
Lossless target PNGs and a gold-blind input manifest are written **outside Git**.
No target means no crop or rerank. Existing Qwen B reader crops are a separate
diagnostic: B's detector/Top20 differ and cannot establish an ORT6 gain.

Reader prompt is candidate-blind; per-line literal text, crop SHA, polygon
(`null` unless OCR actually provides it), recognition confidence (`null` for
Qwen text), and field state (`observed` / `unknown`) stay in the
observation card. A catalog value is `source=organizer_card`,
`verification=unknown` unless an independent source checks it. A missing
variety on a label or incomplete blend never establishes a contradiction.

Example schema with a **public-only, illustrative** input (no private label):

```json
{"query_sha256":"<public SHA>","target_box":[0,0,100,200],"crop_sha256":"<target PNG SHA>","observations":[{"literal_text":"RIESLING","polygon":null,"source_crop_sha256":"<target PNG SHA>","recognition_confidence":null,"field":"grape","field_status":"observed"}]}
```

This is an offline rerank experiment; cached-stage timing is not HTTP timing.
No durable tests are part of this task.

## Reproduction and provenance

1. `prepare.py` seals public manifest + historical ORT6 HTTP raw + metadata
   using exact case, query SHA, track, and **whole-branch Top20 equality**.
   Target boxes and crop PNGs come from that same ORT6 route.
2. `reader_view.py` produces JPEG quality 90, maximum edge 768, and records
   both origin PNG and actual reader JPEG hashes. `reader_inputs.py` removes
   all candidate data before shipping the images and manifest to the GPU.
3. Run the pinned Qwen target-only reader from `../night-reader/read.py` against
   those JPEG bytes. The runtime owner's Paddle OCR runs on the **identical**
   JPEG bytes; `cpu_input.py` preserves its OCR polygon and confidence and
   fills genuinely missing targets with neutral `no_target` rows.
4. `match.py` uses only evidence from the target view. Distinct title tokens
   outrank generic grape matches within the original Top1 producer family;
   uncertain OCR words do not affect ranking. A one-variety contradiction
   requires the same variety in both the catalog's explicit grape field and
   its title. An incomplete blend or missing variety is `unknown`.
5. `export.py` seals each dataset/reader separately, with fixed input pool,
   reader stage timings, catalog/index/model/source hashes and adjacent receipt.
   `http_status` / `elapsed_ms` are deliberately null because this offline
   export predates the separate full R1 HTTP run. Baseline ORT6 HTTP fields
   are recorded separately.
6. If independent ORT6 metadata for the remaining organizer cases arrives,
   `complete.py` copies existing reader JPEG bytes unchanged and creates only
   missing views. Reader/OCR run only for the newly eligible cases. The final
   manifest and all receipts get new hashes. `public_example.py` writes a
   real observation card **outside Git**, without catalog candidates or gold.

Earlier partial v3/v4 exports were revoked. Partial v5 explicitly records 19
organizer `metadata_missing / not_run` rows, not `no_target`. Full v6 uses the
independently captured ORT6 metadata for all 103 organizer IDs, preserving all
previous JPEG bytes. A separate public-only duplicate-photo provenance receipt
checks every repeated organizer query SHA against independent per-ID target
boxes, original Top20, and reader JPEG hashes. Full raw and receipts are stored
next to the reader views outside Git.

`http_harness.py` and `http_client.py` are an isolated, optional **full-frame
HTTP timing experiment**. They must run on owner-released hardware with real
ORT6 assets plus the pinned GPU reader. The HTTP server refuses any mismatch
against the fixed ORT6 Top20, target box, or JPEG SHA. The client compares
each HTTP prediction with the sealed offline GPU prediction and records full
wall-clock and cold startup separately.

`trace.py` joins the already sealed public v6 scorer raw with its fixed input
manifest and hardware/timing receipt into 316 per-request, gold-blind decision
traces for each reader variant; its JSONL and receipt remain outside Git. A
trace records input/target hashes, literal reader observations (or an explicit
unknown), fixed Top20, matcher evidence and rerank reason, final result, and
the applicable offline timing scope. The isolated HTTP run embeds analogous
evidence in the same request/response pass; no additional inference is needed.

## Isolated full HTTP run · 26 September 2026

The owner released Pod B for a single 316-request sequential full-frame run
on loopback port 8786. Mac artifacts, outside Git:
`/Users/skif/ml-data/brutforce/ml086-r1-20260926-reader-view-full/http-full316-v1.jsonl`
(SHA256 `3712cb169c6705b402e8465a0ce23fd642268bdc7ba13ab301fac9c4b3635c56`),
the adjacent `.receipt.json` (SHA256 `756607f1e06197b1be7ef2a8922db8ff2119cad0181e407c665d9e504ff0b796`),
and `http-full316-v1-cold-context.receipt.json` (SHA256
`d7cc0d22e10f1c6fd50eff67831cf280943446cef0bc3e5f81c2477c1312ce70`).
The separate `http-full316-v1-startup-failure.receipt.json` (SHA256
`c4d0712b309d5cf256853e90704a1ea9ca4ce6fe72b6ade257f19e089302684f`)
records the first offline cold-start failure: a Qwen-only `HF_HOME` hid the
existing ORT6 OWLv2 cache. The owner-approved default-cache Qwen symlink
repaired this without a download or source change. Exact failed-start elapsed
and a complete pre-run Pod B model-byte hash manifest were not recorded; the
receipt marks both missing rather than substituting historical Sigma hashes.
All 316 requests returned HTTP 200 and matched the sealed v6 prediction;
query SHA, selected box, fixed Top20, and reader JPEG SHA matched 316/316.
Full-request p50/p95/max was 2.882/4.450/6.049 seconds, with 0 requests
over 8.5 or 10 seconds. The 316-request client wall total was 953.359 seconds.
Startup loads were measured separately (ORT6 17.648 seconds, Qwen 10.772
seconds). The contract smoke prewarmed the models before the timed run, so
the fields named `cold_first_request` in the original receipt denote first
within the run, **not** actual cold end-to-end HTTP latency; the cold-context
receipt explicitly records this limitation. Product GO requires trusted
aggregate scoring and the coordinator's decision.

Trusted independent audit accepted the HTTP raw, receipts, provenance and
316/316 sealed v6 parity. Quality was unchanged from the offline v6 result:
organizer exact 43/54 versus ORT6 39/54, with 4 fixed, 0 broken across 3
independent groups; frozen service 115/141 versus 110/141; retrieval 59/62
versus 56/62; OOD 0/1 unchanged. Frozen and organizer HTTP p95 were 4.388
and 4.872 seconds respectively. The scorer withheld **release GO** pending
independent deployment-hardware/OOD validation and the reused-dev caveat;
the coordinator owns the final product decision.
