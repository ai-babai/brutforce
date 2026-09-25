# Isolated Sigma CPU benchmark tools

These scripts test frozen vision pipelines without changing the shared TEST or
PROD service. `night_server.py` hosts one CPU request at a time on loopback;
`run_http.py` sends the pinned public inputs once each and saves every HTTP
status, wall time, and response to JSONL. `analyze_rows.py` summarizes both
latency and deadline failures. `export_predictions.py` creates complete v2
submissions from saved rows. The two `score_*.py` programs run only on the Mac
after inference and require private labels; they are never service dependencies.

## Profiles

| Route | Detector/gate | Visual embedding | OCR |
| --- | --- | --- | --- |
| `owl640` | RT-DETR + Base224 wine gate; 640px OWLv2 no-bottle fallback | SO400M/384 whole target | Off by default |
| `fullframe` | RT-DETR + Base224; full-frame fallback for no bottle | SO400M/384 whole target | Paddle only to confirm full-frame fallbacks |
| `softgate` | `owl640` plus generic wine-text evidence for rejected bottle candidates | SO400M/384 whole target | Paddle only on candidates passing the soft-gate checks |
| `onnx640` | Same as `owl640` | FP32 ONNX Runtime SO400M/384 batch-one graph | Off |
| `onnx_dual` | Same as `onnx640`; OWLv2-640 also finds a target-label crop | FP32 ONNX Runtime SO400M whole and label views, weighted RRF | Off |
| `onnx_int8` | Same target selector as `onnx640` | Dynamic QInt8 SO400M query encoder with unchanged FP32 catalog index; separate quality profile | Off |

The existing Base224 `standard`/`owl640` controls remain available for paired
latency and quality measurements. No route trains weights or changes the
reference index. The SO400M index contains 2,103 catalog slugs; 2,060 rows are
finite and 43 are masked unavailable. The Base224 comparison uses a separately
verified index with the same catalog and availability mask.

## Inputs and isolation

- Frozen v2 public manifest: `/Users/skif/ml-data/brutforce/night-20260925/cpu/public-v2.json`
  (213 cases: 151 service, 62 retrieval).
- Organizer public manifest: `/Users/skif/ml-data/brutforce/night-20260925/cpu/organizer-public.json`
  (103 requests, 100 unique image SHA-256 values).
- Sigma catalog: `/srv/lct/data/vision-retrieval/20260925/detectors/catalog-audit/catalog-bundle.json`.
- Sigma SO400M index: `/srv/lct/data/vision-retrieval/20260925/detectors/so400m-gatev2/index`.
- Sigma private benchmark workspace: `/srv/lct/data/vision-service/benchmarks/night-20260925-cpu/`.
- Local artifact workspace: `/Users/skif/ml-data/brutforce/night-20260925/cpu/`.
- Experimental main port `8127`; Paddle worker port `8129`. Both bind loopback.

The pinned SO400M model is `google/siglip2-so400m-patch16-384` revision
`dd658faac399427308559e2c3ac1e99cbe43845d`. `onnx_so_pipeline.py`
uses the saved processor and exact FP32 graph; its weights and SHA are recorded
in the local report. ORT dependencies belong in a separate `--target` directory,
never in the shared vision-service virtualenv.

## Repeatable measurement

Run an isolated server with `night_server.py --encoder so400m --route owl640
--threads 6` and the pinned `--catalog`/`--index-dir` above. Use `run_http.py`
with `--manifest`, `--image-root`, `--out`, `--run-id`, `--variant`, and
`--url http://127.0.0.1:8127/v1/eval/predict`. The runner checks each input
SHA and issues one request with a 10-second socket timeout, then waits for the
service's inference slot to become idle. Submission export also enforces the
10-second total elapsed deadline to match the organizer's `curl --max-time 10`.
See the artifact report for exact full-run commands, hashes, resource limits,
failure IDs, and source snapshots.

For the ONNX routes, the immutable local
`runtime-provenance-lock.json` records the graph, processor, catalog, index,
model revisions, source-module hashes, thread counts, and unit limits. The
`source-ort6/` and `source-ortdual/` folders are snapshots of the code used by
each run. `ortdual-systemd-units.txt` preserves the complete transient unit
configuration, including environment variables and command arguments. The
`ort6-publication-provenance.json` sidecar hashes the already-published ORT6
submissions, their raw full HTTP rows, and the runtime lock; the published
submission files are unchanged. The
ONNX graph lives at
`/srv/lct/data/vision-retrieval/night-20260925/onnx/vision.onnx`; its SHA-256
is `d98c21ec54cda834d57fe2ad3151eb19d4d23b211ecad713844a10263828bd80`.
These files are under `/Users/skif/ml-data/brutforce/night-20260925/cpu/`.

The original organizer `participant_test.sh` is a separate compatibility smoke
test through an SSH tunnel. Its JSONL `predicted_slug: null` cannot distinguish
an expected no-match action from a timeout; use the raw HTTP rows for that.

## Acceptance observations, 2026-09-25

The unchanged organizer script completed a 12-case service sample for both
SO400M+OWL640 PyTorch and the FP32 ONNX Runtime 6-thread route. The sample
includes all five previous CPU timeout inputs. Every script slug matched the
corresponding full raw HTTP response; neither script run exceeded ten seconds.
The PyTorch sample maximum was 6.069 seconds and the ONNX sample maximum was
5.534 seconds. These were carried through an SSH tunnel to the isolated
loopback service, not a public TLS endpoint.

Two simultaneous clients to the 6-thread ONNX route returned one `503 busy`
in 57 ms and one `200` in 4.76 s. A follow-up request succeeded with `200` in
3.26 s. This service has one inference slot; concurrent arrivals need caller
queuing or a wider serving design. Raw probe results and the original script
JSONL are in the local artifact workspace. The full frozen and organizer
benchmarks were sequential, one request at a time.

The local
`/Users/skif/ml-data/brutforce/night-20260925/cpu/ORGANIZER-GAP-DIAGNOSTIC.md`
joins CPU ORT6, GPU cached whole, and GPU B fused organizer outputs by image
SHA-256. It keeps reviewed labels and raw case details outside Git, and
distinguishes target-selection differences from the label/OCR ranking changes.

The bounded `onnx_int8` control is documented in the same local `RESULTS.md`.
It was faster on the full frozen HTTP run but lost substantial accuracy against
the fixed FP32 index. This rejects that **mixed-precision pairing**, not all
INT8 implementations or a separately built INT8 reference index. Its full
raw rows, submissions, source snapshot, converter receipt, and exact runtime
manifest are under the local `cpu/` artifact workspace. No organizer run was
spent on the failed profile.
