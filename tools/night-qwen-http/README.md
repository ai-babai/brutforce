# Fresh B → Qwen3-VL Top20 HTTP validation

This independent N3 runtime check sends the original 316 image bytes to a
locally warmed B HTTP server. B selects a target, runs PaddleOCR and visual
retrieval, and supplies its current Top20. The Qwen3-VL-Reranker-2B HTTP
process crops that target from the original image, compares each fixed B
candidate with its catalog reference card/photo, and returns a reranked Top20.
No cached B answer, query label, or gold record enters either endpoint.

Official Qwen checkpoint revision:
`Qwen/Qwen3-VL-Reranker-2B@4bd860ac4f15ad1897a214615cccc700f8f71818`.
The Qwen implementation and fixed instruction are inherited from the pinned
upstream repository and this session's `tools/night-experiments/qwen_rerank.py`.
`server.py` uses the same BF16 batch-1 scoring and validated one-patch
Conv3d→linear projection as that offline run. The B source is commit `591e8c8`
with the same exact SO400M gate-v2 index, catalog SHA, and four pinned HF model
snapshots as the prior B run. Query crops are computed after fresh B inference.

`run_suite.py` is an **uncapped diagnostic**: its 180-second socket timeout is
not a 10-second service deadline. `project_deadline.py` retrospectively
counts every observed response over 10 seconds as an error; this is a
conservative projection, not a live deadline test. `run_suite_strict.py`
was an engineering probe retained in the artifacts. The final strict driver
`run_suite_curl.py` uses curl's absolute `--max-time 10` transaction deadline,
also checks total client wall time, and waits for the single-threaded server
to drain after each timeout before sending another image. These runs have
separately named exports and scores.

`server_rich.py` is a separate exploratory profile. It appends the original
catalog `reference_filename` field uniformly to every document description
and uses `cards-rich.json`. The baseline `server.py` and original cards remain
frozen for the first two HTTP captures.

`server_website.py` is another separate profile. It starts from baseline
cards and appends only two public catalog fields,
`website_category_and_sweetness` and `website_sweetness`, where a catalog
identity join was verified. Unmatched or conflicting slugs have no extra
fields. It uses `cards-website.json`, whose SHA and mapping receipt are in
the stage directory.

Each strict export requires a `runtime-*.json` receipt binding the exact B
source, catalog/index, OCR and OMP thread settings, Qwen checkpoint and card
SHA, and client deadline into `config_hash`. OMP1 and website metadata have
separate profile names, source snapshots, captures, submissions, and scores.

## Replay recipe

The recorded RTX 3090 pod used Python 3.12, torch 2.9.1+cu128,
Transformers 4.57.6, PaddlePaddle 3.3.0, PaddleOCR 3.7.0, PaddleX 3.7.2.
The exact `pip freeze`, CUDA driver, cgroup CPU quota, health responses,
source SHA list, and complete launch commands are preserved under the local
artifact directory `night-20260925/qwen-http/runtime/`. The following paths
are staging locations on a replay GPU host; transfer data over SSH or rsync,
with no gold or sealed labels on that host.

```sh
# Stage these immutable inputs on the GPU host:
# /workspace/b/code: extract b-source-591e8c8.tar, SHA
#   f4025157acb2b3a78de12cac38a805c3d9a12f90e6cf081aaf9d1815120bdae9
#   (local: night-20260925/roman/b-source-591e8c8.tar)
# /workspace/b/index/index: Sigma source
#   /srv/lct/data/vision-retrieval/20260925/detectors/so400m-gatev2/index
# /workspace/b/catalog/catalog-bundle.json: Sigma source
#   /srv/lct/data/vision-retrieval/night-20260925-lightglue/stage/catalog-bundle.json
#   SHA a52c6a087509c62b2d961a315e563e7093838a795fc50437f813a6a654f677b2
# /workspace/qwen/refs: images/ from local common/reference-stage.tar.gz
#   archive SHA 8ffcbfc8cbf2aec78ebc4103efb7706b508e3e3640fb0d6a65b80d5e0fa53b67
# /workspace/qwen/stage/inputs.jsonl: public 316-row five-field replay
#   manifest, local qwen-http/inputs-minimal-public.jsonl SHA
#   ebba1948667b4bbb768e552dd4d5f80bc9396477521f23279f7ee8e6e3d05706
# /root/b-queries: 316 original query images, SHA checked against inputs.jsonl
# /workspace/qwen/stage/cards.json: baseline card SHA
#   5ffb93714c611efbe541028f44dff84dfc0646451c364caee979869d1548be9a
# /workspace/qwen/stage/cards-website.json: optional metadata card SHA
#   1520355a0ef1f24788cd4ba5fe91f566d7c6d214927349765ac51f95482d2ebd
# /workspace/qwen/upstream: local
#   night-20260925/qwen/upstream implementation snapshot.
# /workspace/b/qwen_http_server.py, qwen_http_server_website.py,
#   run_suite_curl.py: copy this module's matching source files.

# After transferring the listed local archives/files to the GPU host:
mkdir -p /workspace/b/code /workspace/qwen/reference-stage /workspace/qwen/stage
tar -xf /workspace/b/b-source-591e8c8.tar -C /workspace/b/code
tar -xzf /workspace/qwen/reference-stage.tar.gz -C /workspace/qwen/reference-stage
cp /workspace/qwen/reference-stage/catalog-bundle.json /workspace/b/catalog/catalog-bundle.json
cp -a /workspace/qwen/reference-stage/images/. /workspace/qwen/refs/
# Copy the SO400M index directory itself to /workspace/b/index/index.
# Copy the local cards.json, cards-website.json, inputs.jsonl and query images
# to their listed GPU paths; verify all SHA values before inference.

# Install B in an isolated Python 3.12 venv, using the recorded source files.
python3 -m venv --system-site-packages /root/b-venv
/root/b-venv/bin/pip install -r /workspace/b/code/tools/vision-retrieval/requirements.txt \
  -r /workspace/b/code/tools/vision-retrieval/requirements-ocr.txt

# On the recorded RunPod Python 3.12 / torch 2.9.1+cu128 base image:
python3 -m venv --system-site-packages /workspace/qwen/venv
/workspace/qwen/venv/bin/pip install 'transformers==4.57.6' \
  'accelerate==1.15.0' 'qwen-vl-utils==0.0.14'
# Compare the installed environment with runtime/qwen-pip-freeze.txt.

# Populate the default Hugging Face cache with exact model revisions:
# PekingU/rtdetr_r18vd@ac77a11ff0170a41b771c03264987f8ce2b0d753
# google/owlv2-base-patch16-ensemble@cfd3195ba4ea9592eec887ded089f4c08eff231d
# google/siglip2-base-patch16-224@75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2
# google/siglip2-so400m-patch16-384@dd658faac399427308559e2c3ac1e99cbe43845d
# Qwen/Qwen3-VL-Reranker-2B@4bd860ac4f15ad1897a214615cccc700f8f71818
# PaddleX mobile recognition cache: eslav_PP-OCRv5_mobile_rec;
# mobile detector PP-OCRv5_mobile_det may download on first cold load.
/root/b-venv/bin/hf download PekingU/rtdetr_r18vd --revision ac77a11ff0170a41b771c03264987f8ce2b0d753
/root/b-venv/bin/hf download google/owlv2-base-patch16-ensemble --revision cfd3195ba4ea9592eec887ded089f4c08eff231d
/root/b-venv/bin/hf download google/siglip2-base-patch16-224 --revision 75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2
/root/b-venv/bin/hf download google/siglip2-so400m-patch16-384 --revision dd658faac399427308559e2c3ac1e99cbe43845d
/workspace/qwen/venv/bin/hf download Qwen/Qwen3-VL-Reranker-2B --revision 4bd860ac4f15ad1897a214615cccc700f8f71818

cd /workspace/b/code/tools/vision-retrieval
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True /root/b-venv/bin/python -u \
  softgate_server.py --catalog /workspace/b/catalog/catalog-bundle.json \
  --index-dir /workspace/b/index/index --device cuda --ocr-threads 2 \
  --host 127.0.0.1 --port 8091

# In another terminal, using the recorded Qwen venv/package list:
/workspace/qwen/venv/bin/python -u /workspace/b/qwen_http_server.py \
  --cards /workspace/qwen/stage/cards.json --references /workspace/qwen/refs \
  --upstream /workspace/qwen/upstream --b-url http://127.0.0.1:8091 \
  --host 127.0.0.1 --port 8092

# Baseline strict capture. For website, replace wrapper source with
# qwen_http_server_website.py and cards with cards-website.json, restart it,
# and write to a new output file.
python3 /workspace/b/run_suite_curl.py \
  --inputs /workspace/qwen/stage/inputs.jsonl --queries /root/b-queries \
  --url http://127.0.0.1:8092 --out /workspace/b/results/http-strict10-curl.jsonl
```

The recorded runs used the older staging `inputs.jsonl` SHA
`455efcb9c45a5bf374dc437f0365f88cb2aa6b368b9b80ce988e3f3643c31fdc`,
which also contained cached B diagnostic rows. Those rows were unused:
`run_suite_curl.py` lines 29–53 accesses only `case_id`, `query_path`,
`query_sha256`, `track`, and later `dataset` for the output row. It verifies
the query image SHA and POSTs only the image file bytes. `server.py` lines
165–180 receives only that raw body and track; lines 108–145 calls B afresh,
then uses its current `ranked_slugs`, crop box, catalog card, and reference
photo. `server_website.py` has the same call graph plus two public card
fields. The five-field replay manifest above makes this boundary explicit.
No gold or sealed labels were staged on the GPU host. Trusted scorers run
only after capture on the local machine.

Local export and trusted scoring happen **after** copying the raw JSONL back
from the GPU host. `ART` is the local `night-20260925/qwen-http` directory;
`EVAL` is the local `brutforce-eval` repository root.

```sh
python3 "$EVAL/tools/night-qwen-http/export.py" --raw "$ART/http-strict10-curl.jsonl" \
  --mode service --profile strict-10s \
  --runtime-receipt "$ART/runtime-strict-10s.json" \
  --suite "$ART/../common/suite-v2/baskets/v2.json" \
  --submission-id qwen-http-strict10-service \
  --out "$ART/submission-strict-10s-service-v2.json"
python3 "$EVAL/tools/night-cpu/score_frozen.py" \
  --gold "$ART/../cpu/.scorer/gold-v2.json" \
  --manifest "$ART/../cpu/public-v2.json" \
  --submission "$ART/submission-strict-10s-service-v2.json" \
  --out "$ART/private-score-strict-10s-service.json"

# Repeat export+score for retrieval with --mode retrieval and a new ID/output.
python3 "$EVAL/tools/night-qwen-http/export.py" --raw "$ART/http-strict10-curl.jsonl" \
  --mode organizer --profile strict-10s \
  --runtime-receipt "$ART/runtime-strict-10s.json" \
  --out "$ART/organizer-strict-10s.jsonl"
python3 "$EVAL/tools/night-cpu/score_organizer.py" \
  --manifest "$ART/../cpu/organizer-public.json" \
  --predictions "$ART/organizer-strict-10s.jsonl" \
  --labels "$ART/../../vision-retrieval-20260925/annotation/sealed-v1.jsonl" \
  --overlay "$ART/../../vision-retrieval-20260925/absence-audit/parent-accepted-overlay-v1.json" \
  --profile qwen-http-strict10 --out "$ART/private-score-organizer-strict-10s.json"
```
