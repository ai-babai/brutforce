#!/usr/bin/env bash
# Native Apple Silicon photo scoring: F8 vision and contest API, without a database or UI.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
action=${1:-up}
case "$action" in
  up) data_root=${2:-"$HOME/ml-data/brutforce/local-demo"}; archive_arg=${3:-} ;;
  photo) photo=${2:?Usage: bash scripts/bootstrap-mac.sh photo /absolute/photo.jpg [data-root]}
         data_root=${3:-"$HOME/ml-data/brutforce/local-demo"} ;;
  stop) data_root=${2:-"$HOME/ml-data/brutforce/local-demo"} ;;
  *) echo 'Usage: bash scripts/bootstrap-mac.sh [up [data-root [archives]] | photo FILE [data-root] | stop [data-root]]' >&2; exit 1 ;;
esac

[[ "$data_root" = /* ]] || { echo 'Data root must be an absolute path' >&2; exit 1; }
if [[ "$action" == up ]]; then
  mkdir -p "$data_root"
fi
[[ -d "$data_root" ]] || { echo "Data root not found: $data_root" >&2; exit 1; }
data_root=$(cd -- "$data_root" && pwd -P)
case "$data_root/" in "$root/"*) echo 'Data must live outside the clone' >&2; exit 1;; esac
native="$data_root/mac-scoring"

is_ours() {
  [[ "$1" =~ ^[0-9]+$ ]] && ps -p "$1" -o command= 2>/dev/null | grep -F -- "$2" >/dev/null
}

stop_one() {
  local name=$1 marker=$2 pidfile="$native/run/$1.pid" pid
  [[ -f "$pidfile" ]] || return 0
  pid=$(<"$pidfile")
  if is_ours "$pid" "$marker"; then
    kill "$pid"
    echo "Stopped $name ($pid)"
  fi
  rm -f "$pidfile"
}

if [[ "$action" == stop ]]; then
  stop_one api "$native/bin/scoring-api"
  stop_one vision "$root/apps/vision/overlay/night_server.py"
  exit
fi
if [[ "$action" == photo ]]; then
  [[ -f "$photo" ]] || { echo "Photo not found: $photo" >&2; exit 1; }
  curl --fail-with-body --show-error --silent --max-time 30 \
    -F "image=@$photo" http://127.0.0.1:8097/v1/eval/predict
  exit
fi

[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || {
  echo 'Native scoring requires an Apple Silicon Mac' >&2; exit 1;
}
for tool in uv go tesseract curl tar lsof shasum; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (install uv, go, tesseract with Homebrew)" >&2; exit 1; }
done
mkdir -p "$native/run" "$native/logs" "$native/bin"
if [[ ! -x "$native/venv/bin/python" ]]; then
  uv venv --python 3.12 "$native/venv"
fi

if [[ ! -f "$data_root/f8-bundle/onnx/vision.onnx" ]]; then
  if [[ -n "$archive_arg" ]]; then
    archives=$(cd -- "$archive_arg" && pwd -P)
    mode=offline
  else
    archives="$data_root/archives"
    mkdir -p "$archives"
    mode=download
  fi
  "$native/venv/bin/python" "$root/scripts/bootstrap-assets.py" "$archives" "$mode" scoring
  tar -xf "$archives/01-recognition-data.tar.gz" -C "$data_root"
  cat "$archives"/02-recognition-weights.tar.part-00{0..5} | tar -xf - -C "$data_root"
fi
"$native/venv/bin/python" "$root/scripts/asset-bundle.py" verify "$data_root/f8-bundle"

requirements="$root/deploy/assets/vision-requirements-mac.txt"
stamp=$(shasum -a 256 "$requirements" | cut -d' ' -f1)
if [[ ! -f "$native/run/requirements.sha256" || $(<"$native/run/requirements.sha256") != "$stamp" ]]; then
  uv pip sync --python "$native/venv/bin/python" "$requirements"
  printf '%s\n' "$stamp" > "$native/run/requirements.sha256"
fi

api_pidfile="$native/run/api.pid"
vision_pidfile="$native/run/vision.pid"
if [[ -f "$api_pidfile" && -f "$vision_pidfile" ]] && \
   is_ours "$(<"$api_pidfile")" "$native/bin/scoring-api" && \
   is_ours "$(<"$vision_pidfile")" "$root/apps/vision/overlay/night_server.py" && \
   curl --fail --silent --max-time 2 http://127.0.0.1:8126/healthz >/dev/null && \
   curl --fail --silent --max-time 2 http://127.0.0.1:8097/v1/health >/dev/null; then
  echo 'Scoring already running at http://127.0.0.1:8097/v1/eval/predict'
  exit
fi
# Stop only processes recorded by this bootstrap; never take over another service's port.
stop_one api "$native/bin/scoring-api"
stop_one vision "$root/apps/vision/overlay/night_server.py"
for port in 8126 8097; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null; then
    echo "Port $port is already in use; stop its owner before starting scoring" >&2
    exit 1
  fi
done

export HF_HOME="$data_root/f8-bundle/models"
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 NIGHT_SO_ONNX_THREADS=6
export NIGHT_SO_ONNX_DIR="$data_root/f8-bundle/onnx"
export F0_BASE_CODE_DIR="$root/apps/vision/parent"
export F8_OCR_LEXICON_SPEC="$root/apps/vision/overlay/spec/lexicon.json"
export TESSDATA_PREFIX="$data_root/f8-bundle/ocr"
export PYTHONPATH="$root/apps/vision/parent"

cleanup() {
  stop_one api "$native/bin/scoring-api"
  stop_one vision "$root/apps/vision/overlay/night_server.py"
}
trap cleanup EXIT
"$native/venv/bin/python" "$root/apps/vision/overlay/night_server.py" \
  --catalog "$data_root/f8-bundle/catalog/catalog-bundle.json" \
  --index-dir "$data_root/f8-bundle/index" --host 127.0.0.1 --port 8126 \
  --threads 6 --encoder so400m --route onnx640 > "$native/logs/vision.log" 2>&1 &
printf '%s\n' "$!" > "$vision_pidfile"
for attempt in {1..90}; do
  if curl --fail --silent --max-time 2 http://127.0.0.1:8126/healthz >/dev/null; then break; fi
  if ! is_ours "$(<"$vision_pidfile")" "$root/apps/vision/overlay/night_server.py"; then
    echo "Vision exited; see $native/logs/vision.log" >&2; exit 1
  fi
  if [[ "$attempt" == 90 ]]; then echo "Vision timed out; see $native/logs/vision.log" >&2; exit 1; fi
  sleep 1
done

(cd "$root/apps/api" && go build -o "$native/bin/scoring-api" .)
env -u DATABASE_URL -u WEB_ROOT -u RECOMMENDATION_INDEX_FILE \
  ADDRESS=127.0.0.1:8097 VISION_SERVICE_URL=http://127.0.0.1:8126 \
  VISION_CATALOG_VERSION=organizer-catalog-20260919 \
  VISION_INDEX_VERSION=so400m384-owlv2-v2-crops-reference-gated-20260925 \
  VISION_SLUGS_FILE="$data_root/f8-bundle/overlay/organizer-slugs.json" \
  VISION_SLUGS_SHA256=b0d1ce3d493bdae9307e1d83138049638d9cee52b2f203dca85d67f67e516dfd \
  "$native/bin/scoring-api" > "$native/logs/api.log" 2>&1 &
printf '%s\n' "$!" > "$api_pidfile"
for attempt in {1..30}; do
  if curl --fail --silent --max-time 2 http://127.0.0.1:8097/v1/health >/dev/null; then break; fi
  if ! is_ours "$(<"$api_pidfile")" "$native/bin/scoring-api"; then
    echo "API exited; see $native/logs/api.log" >&2; exit 1
  fi
  if [[ "$attempt" == 30 ]]; then echo "API timed out; see $native/logs/api.log" >&2; exit 1; fi
  sleep 1
done
trap - EXIT
echo 'Scoring ready: bash scripts/bootstrap-mac.sh photo /absolute/photo.jpg'
echo 'Stop: bash scripts/bootstrap-mac.sh stop'
