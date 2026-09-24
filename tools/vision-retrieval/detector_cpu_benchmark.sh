#!/usr/bin/env bash
# Same-host, same-manifest full HTTP CPU timing for a detector variant.
set -euo pipefail

variant=${1:?variant required}
out=${2:?output JSON required}
root=${LCT_EXPERIMENT_ROOT:-/workspace/lct-detectors}
code="$root/tools/vision-retrieval"
index="$root/data/index-v2"
url=http://127.0.0.1:8080/v1/eval/predict
mkdir -p "$(dirname "$out")"
cd "$code"
export HF_HOME="$root/hf" YOLO_CONFIG_DIR="$root/ultralytics"
export OMP_NUM_THREADS=4 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
if [[ "$variant" == owlv2 ]]; then
  "$root/venv/bin/python" server.py --catalog "$root/data/catalog/catalog-bundle.json" \
    --index-dir "$index" --device cpu --ocr-threads 2 --label-context \
    --host 127.0.0.1 --port 8080 > "${out%.json}-server.log" 2>&1 &
else
  "$root/venv/bin/python" detector_server.py --variant "$variant" \
    --catalog "$root/data/catalog/catalog-bundle.json" --index-dir "$index" \
    --device cpu --ocr-threads 2 --host 127.0.0.1 --port 8080 \
    > "${out%.json}-server.log" 2>&1 &
fi
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
trap cleanup EXIT
ready=0
for ((i=0;i<120;i++)); do
  if curl -fsS http://127.0.0.1:8080/healthz > "${out%.json}-health.json" 2>/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  cat "${out%.json}-server.log" >&2
  exit 1
fi
"$root/venv/bin/python" "$root/tools/organizer-audit/benchmark_pipeline.py" \
  --manifest "$root/data/organizer/benchmark-queries.json" \
  --image-root "$root/data/organizer" --url "$url" --hardware-label rtx4090-pod-cpu4 \
  --device cpu --cpu-threads 2 --omp-threads 4 \
  --code-sha256 "$(sha256sum "$code/detector_variants.py" | cut -d' ' -f1)" \
  --index-sha256 "$(sha256sum "$index/index.npz" | cut -d' ' -f1)" \
  --out "$out" --limit 24 --timeout 120
