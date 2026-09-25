# N4 Roman comparison

Gold-blind, isolated experiment. `prepare.py` binds all 213 frozen v2 and 103
organizer requests to the saved B candidate pool. `run.py --phase five` and
`run.py --phase twenty` apply Roman's white-background full-frame bound with
Pillow 12.3 from original query bytes and perform GPU inference. `merge.py`
joins the two passes, and `finalize.py` exports
full-basket predictions and separate service/retrieval submissions.

```text
original full frame → B RT-DETR / SigLIP2 / OCR → fixed Top20 and RRF scores
  ├─ no new judge: B control
  ├─ first five → pinned Qwen3.5-4B with LoRA disabled → base control
  ├─ first five → same base + Roman fullframe LoRA → Roman-5
  └─ four five-card groups from Top20 → winners + B top1 / original five
      → same Roman adapter final five → Roman-20
```

Roman-5 and Roman-20 share the *same* previously trained adapter, SHA
`d0aab163ed839cd9f759654f0834d672f47d7a6ddd5510925d904fc55b84e3e4`.
They differ in pool/tournament. Base revision is
`Qwen/Qwen3.5-4B@851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`.
No model training is performed.

The prompt, public card fields, shuffled choice order, 131072-pixel reference
bound, 524288-pixel Qwen processor bound, six digit logits, NF4 double
quantization and BF16 follow the handoff. B RRF scores are divided by their
row maximum before the original Roman gates (`.7/.025` for five and `.9/.4`
for twenty) because their raw scale differs from Roman's 590 score matrix.
This is a prespecified transfer policy, not a replay of Roman's 715/2033
development result. Roman-only catalog gaps use public organizer metadata when
an exact gate-v2 reference exists. Excluded references are never substituted.

The GPU runtime replaces the vision patch encoder's non-overlapping Conv3d
with the corresponding matrix multiplication (`F.linear`) using identical
weight and bias tensors. The BF16 patch outputs differed by at most 0.00390625
in the first eight-patch check. A full-model check also records six logits
from the original and accelerated kernels. Triton uses each kernel's first
supplied configuration because its default first-call autotuning stalled for
over five minutes. This is an explicit **runtime-linear** execution variant,
not a bitwise replay of Roman's original inference backend.

If B has no candidate, or a required reference is excluded, the corresponding
profile retains B's output and records the fallback reason. Every original
request remains in exported predictions and denominators. Submission latency
records the Qwen processor plus model call after query/reference decode and
card assembly. B's earlier recorded HTTP time and whole Roman row time are
retained separately in paired predictions. These latencies are not a public
end-to-end endpoint measurement.

The immutable handoff lacks the ancestor
`geometry-view-route-full715-v1/evaluation/scores.npy` and
`candidate-coverage-590-v1/pools.npz`, so Roman's native 590 cascade cannot be
reconstructed from this package. Keep these results labeled **Roman judge over
B pool**. Never transfer gold to the GPU. Score only after predictions are
frozen and copied to the trusted local evaluator.

## Fresh HTTP cascade

`prepare_online.py` exports public case IDs, image hashes, organizer fields,
and reference paths without answer labels. A separate pinned B service loads
the gate-v2 SO400M index, exact 2,060 allowed reference images, RT-DETR,
SigLIP2, and OCR. `online_server.py` calls B by HTTP for each original image,
then runs the Roman adapter on the *fresh* B Top20. Its group-zero Roman-5
result is returned in the same response. `online_client.py` sends all 316
original image bytes with a 10-second client timeout and writes every status.

`online_finalize.py` requires all 316 responses before export. It creates
separate complete frozen service, frozen retrieval, and organizer predictions
for Roman-5 and Roman-20. Its latency is client end-to-end time, including B,
image decode, reference loading, Qwen processor/model, and HTTP transfer.
Roman-5's latency includes the full Roman-20 request because its output is
extracted from that request. This is stated in its solution name. Score only
the locally copied, immutable predictions; no answer labels go to the pod.

## Replay the fresh HTTP experiment

These are the **inference** steps. Run the first block on the Mac and the
second block on a new GPU host; never copy scorer labels or gold to that host.
The only host-specific choices below are `POD_HOST`, `GPU_ROOT`, and the two
venv locations. The frozen local source files and model revisions are actual
inputs, not placeholders. Use an RTX 4090-class GPU with at least 30 GB of
container space and a 60 GB volume. The observed environment and complete
package lists are in
`/Users/skif/ml-data/brutforce/night-20260925/roman/environment/`, including
`roman-pip-freeze.txt`, `b-pip-freeze.txt`, `roman-runtime.txt`,
`b-runtime.txt`, `nvidia-smi.csv`, `cpu-quota.txt`, `memory.txt`, and
`sha256-manifest.json`. This run used Python 3.12.3, Torch 2.9.1+cu128,
Roman Transformers 5.17.0/PEFT 0.21.0/Pillow 12.3.0, and B Transformers
4.57.6/Paddle 3.3.0/PaddleOCR 3.7.0/OpenCV 4.10.0. The OCR detector is
Paddle's official `PP-OCRv5_mobile_det` cold download; the exact recognition
cache is listed below.

```sh
cd /Users/skif/develop/brutforce-eval
python tools/night-roman/prepare.py --out /Users/skif/ml-data/brutforce/night-20260925/roman/input-v1
python tools/night-roman/prepare_online.py --root /Users/skif/ml-data/brutforce/night-20260925/roman

# Sources consumed by prepare.py: frozen public v2 and B predictions under
# /Users/skif/ml-data/brutforce/night-20260925/common/eval-public-v2.json
# /Users/skif/ml-data/brutforce/integration-20260925-1700/model/{softgate-B-eval.jsonl,softgate-B-organizer.jsonl,organizer-public.json,input-stage/}
# plus /Users/skif/ml-data/brutforce/night-20260925/roman/roman-source/
# and /Users/skif/ml-data/brutforce/eval-v1/private/catalog-source/organizer-catalog-20260919.jsonl.
# Catalog source contributes only public card fields and reference paths.
```

The durable, exact-byte transfer assets are
`/Users/skif/ml-data/brutforce/night-20260925/roman/{input-stage.tar,allrefs-gatev2.tar,b-source-591e8c8.tar,replay-assets/}`.
Their checksums and byte lengths are in
`/Users/skif/ml-data/brutforce/night-20260925/roman/replay-assets/asset-manifest.json`.
`allrefs-gatev2.tar` has 2,055 distinct SHA-named reference files for the
2,060 allowed slugs; five slugs share bytes. It came from
`pack_references.py --manifest .../online-input-v1/reference-sources.jsonl`
on Sigma, where those source paths exist. Gate-v2 excludes 23 missing and 20
quarantined catalog rows. Check all tar and index SHA values against the input
provenance and `live-http-v1-provenance/runtime-config.json` before inference.

```sh
# Mac: set only the SSH address/port of the newly provisioned GPU host.
POD_HOST=root@47.47.180.22
POD_PORT=15787
ROMAN_DATA=/Users/skif/ml-data/brutforce/night-20260925/roman
ssh -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -p "$POD_PORT" \
  "$POD_HOST" 'mkdir -p /workspace/night-roman'
scp -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -P "$POD_PORT" \
  "$ROMAN_DATA/input-stage.tar" "$ROMAN_DATA/allrefs-gatev2.tar" \
  "$ROMAN_DATA/b-source-591e8c8.tar" "$POD_HOST:/workspace/night-roman/"
scp -r -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -P "$POD_PORT" \
  "$ROMAN_DATA/replay-assets" "$ROMAN_DATA/online-input-v1" \
  "$ROMAN_DATA/roman-source" "$ROMAN_DATA/environment" \
  "$POD_HOST:/workspace/night-roman/"
scp -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -P "$POD_PORT" \
  /Users/skif/develop/brutforce-eval/tools/night-roman/{online_server.py,online_client.py,organizer_adapter.py,run.py} \
  "$POD_HOST:/workspace/night-roman/"
ssh -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -p "$POD_PORT" \
  "$POD_HOST" 'mkdir -p /root/.paddlex/official_models'
scp -r -i /Users/skif/.runpod/ssh/RunPod-Key-Go -o IdentitiesOnly=yes -P "$POD_PORT" \
  /Users/skif/ml-data/aiijc-2026/weights/paddlex/official_models/eslav_PP-OCRv5_mobile_rec \
  "$POD_HOST:/root/.paddlex/official_models/"
```

```sh
# On the new GPU host, after copying the four durable assets above, the
# online-input-v1/ and roman-source/ directories, and tools/night-roman/*.py
# to GPU_ROOT. Preserve this exact layout.
GPU_ROOT=/workspace/night-roman
ROMAN_VENV="$GPU_ROOT/venv"
B_VENV="$GPU_ROOT/b-runtime/venv"
mkdir -p "$GPU_ROOT/refs" "$GPU_ROOT/b-runtime/index" "$GPU_ROOT/b-runtime/hf"
tar -xf "$GPU_ROOT/input-stage.tar" -C "$GPU_ROOT"
tar -xf "$GPU_ROOT/allrefs-gatev2.tar" -C "$GPU_ROOT/refs"
tar -xf "$GPU_ROOT/b-source-591e8c8.tar" -C "$GPU_ROOT/b-runtime"
cp "$GPU_ROOT/replay-assets/index.npz" "$GPU_ROOT/replay-assets/index-info.json" "$GPU_ROOT/b-runtime/index/"
cp "$GPU_ROOT/replay-assets/catalog-bundle.json" "$GPU_ROOT/b-runtime/"
mkdir -p "$GPU_ROOT/adapter"
cp "$GPU_ROOT/roman-source/adapter_config.json" "$GPU_ROOT/roman-source/adapter_model.safetensors" "$GPU_ROOT/adapter/"

# Install from the archived freeze files into separate Python 3.12 venvs.
python3.12 -m venv "$ROMAN_VENV"
python3.12 -m venv "$B_VENV"
"$ROMAN_VENV/bin/pip" install -r "$GPU_ROOT/environment/roman-pip-freeze.txt"
"$B_VENV/bin/pip" install -r "$GPU_ROOT/environment/b-pip-freeze.txt"
"$ROMAN_VENV/bin/hf" download Qwen/Qwen3.5-4B --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a --local-dir "$GPU_ROOT/base"
"$B_VENV/bin/hf" download google/siglip2-so400m-patch16-384 --revision dd658faac399427308559e2c3ac1e99cbe43845d --cache-dir "$GPU_ROOT/b-runtime/hf"
"$B_VENV/bin/hf" download google/siglip2-base-patch16-224 --revision 75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2 --cache-dir "$GPU_ROOT/b-runtime/hf"
"$B_VENV/bin/hf" download google/owlv2-base-patch16-ensemble --revision cfd3195ba4ea9592eec887ded089f4c08eff231d --cache-dir "$GPU_ROOT/b-runtime/hf"
"$B_VENV/bin/hf" download PekingU/rtdetr_r18vd --revision ac77a11ff0170a41b771c03264987f8ce2b0d753 --cache-dir "$GPU_ROOT/b-runtime/hf"
# Copy the exact local recognition cache into B's Paddle model-cache location:
# /Users/skif/ml-data/aiijc-2026/weights/paddlex/official_models/eslav_PP-OCRv5_mobile_rec
```

Transfer the frozen `environment/` directory along with `roman-source/`.
The original B source
expects the recognition model in PaddleX's official-model cache; inspect
`softgate_server.py` and `environment/b-health.json` after starting B to
verify that OCR loaded, since B can otherwise silently return an OCR-degraded
result. Do not use `FLAGS_use_mkldnn=1`: it raised Paddle's
`ConvertPirAttribute2RuntimeAttribute not support
[pir::ArrayAttribute<pir::DoubleAttribute>]` and changed all five profiled
ranks through the no-OCR fallback.

```sh
# GPU terminal 1: pinned B service, original OCR input and two OCR threads.
cd "$GPU_ROOT/b-runtime/tools/vision-retrieval"
HF_HOME="$GPU_ROOT/b-runtime/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  "$B_VENV/bin/python" -u softgate_server.py --catalog "$GPU_ROOT/b-runtime/catalog-bundle.json" \
  --index-dir "$GPU_ROOT/b-runtime/index" --device cuda --ocr-threads 2 --host 127.0.0.1 --port 8091

# GPU terminal 2: pinned Roman adapter, original B, 20-candidate tournament.
cd "$GPU_ROOT"
"$ROMAN_VENV/bin/python" -u online_server.py --root "$GPU_ROOT" --host 127.0.0.1 --port 8092

# GPU terminal 3: all 316 original images, strict 10-second HTTP client.
cd "$GPU_ROOT"
"$ROMAN_VENV/bin/python" -u online_client.py --root "$GPU_ROOT" --output online-http-316.jsonl --mode twenty

# Separate original-B deadline policy (restart only terminal 2):
"$ROMAN_VENV/bin/python" -u online_server.py --root "$GPU_ROOT" --host 127.0.0.1 --port 8092 --b-skip-threshold-ms 6000
"$ROMAN_VENV/bin/python" -u online_client.py --root "$GPU_ROOT" --output online-deadline6-http-316.jsonl --mode twenty

# Standalone Roman-5 (restart terminal 2 without the threshold):
"$ROMAN_VENV/bin/python" -u online_server.py --root "$GPU_ROOT" --host 127.0.0.1 --port 8092
"$ROMAN_VENV/bin/python" -u online_client.py --root "$GPU_ROOT" --output online-roman5-http-316.jsonl --mode five
```

Copy each immutable 316-row client JSONL and its server sidecar to the Mac
before stopping the GPU. The client file includes every timeout and error;
do not backfill it from late server completions. The published baseline uses
the archived source/config in `live-http-v1-provenance/` and outputs in
`live-http-v1-final/`; quality-changing OCR1280 is separately archived in
`live-ocr1280-provenance/` and `live-ocr1280-final/`. Each replay variant must
have a new `profile_tag`, corresponding `runtime-config.json`, and distinct
output directory. `online_finalize.py` refuses to overwrite and verifies the
source hashes from that config.

```sh
# Trusted Mac only, after copying a complete client file. Example: baseline.
cd /Users/skif/develop/brutforce-eval
python tools/night-roman/online_finalize.py \
  --root /Users/skif/ml-data/brutforce/night-20260925/roman \
  --source /Users/skif/ml-data/brutforce/night-20260925/roman/online-http-316.jsonl \
  --output /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-final \
  --profile-tag live \
  --runtime-config /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-provenance/runtime-config.json \
  --server-source /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-provenance/online_server.py \
  --client-source /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-provenance/online_client.py
python tools/night-cpu/score_frozen.py \
  --gold /Users/skif/ml-data/brutforce/night-20260925/cpu/.scorer/gold-v2.json \
  --manifest /Users/skif/ml-data/brutforce/night-20260925/cpu/public-v2.json \
  --submission /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-final/roman20-service.json \
  --out /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-final/score-roman20-service.json
python tools/night-cpu/score_organizer.py \
  --manifest /Users/skif/ml-data/brutforce/night-20260925/cpu/organizer-public.json \
  --predictions /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-final/roman20-organizer.jsonl \
  --labels /Users/skif/ml-data/brutforce/vision-retrieval-20260925/annotation/sealed-v1.jsonl \
  --overlay /Users/skif/ml-data/brutforce/vision-retrieval-20260925/absence-audit/parent-accepted-overlay-v1.json \
  --profile live-http-v1-roman20 \
  --out /Users/skif/ml-data/brutforce/night-20260925/roman/live-http-v1-final/score-roman20-organizer.json
```

Repeat both scorers for each mode/track. The real organizer multipart adapter
is `organizer_adapter.py`. Its unchanged `participant_test.sh` smoke covers
six public images only; four returned a parsed slug within 10 seconds and
two timed out. See `competition-smoke/report.json`. It is evidence of the
request/response contract on those six images, not full organizer
compatibility or an SLA guarantee.

For the final standalone Roman-5 control, export the copied 316-row file on
the Mac with the single-mode flag, then score its three outputs using the same
local scorer commands above with the corresponding paths:

```sh
cd /Users/skif/develop/brutforce-eval
python tools/night-roman/online_finalize.py \
  --root /Users/skif/ml-data/brutforce/night-20260925/roman \
  --source /Users/skif/ml-data/brutforce/night-20260925/roman/live-roman5-provenance/online-roman5-http-316.jsonl \
  --output /Users/skif/ml-data/brutforce/night-20260925/roman/live-roman5-final \
  --modes roman5 --profile-tag live-roman5 \
  --runtime-config /Users/skif/ml-data/brutforce/night-20260925/roman/live-roman5-provenance/runtime-config.json \
  --server-source /Users/skif/ml-data/brutforce/night-20260925/roman/live-roman5-provenance/online_server.py \
  --client-source /Users/skif/ml-data/brutforce/night-20260925/roman/live-roman5-provenance/online_client.py
```
