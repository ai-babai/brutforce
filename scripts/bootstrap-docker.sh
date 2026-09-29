#!/usr/bin/env bash
# Run the pinned full CPU stack locally. Data and downloaded archives stay outside Git.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
if [[ ${1:-} == photo ]]; then
  photo=${2:?Usage: bash scripts/bootstrap-docker.sh photo /absolute/photo.jpg}
  [[ -f "$photo" ]] || { echo "Photo not found: $photo" >&2; exit 1; }
  [[ -f "$root/deploy/.env.local" ]] || { echo 'Run bootstrap before sending a photo' >&2; exit 1; }
  docker compose --env-file "$root/deploy/.env.local" -f "$root/deploy/compose.yaml" exec -T vision python -c '
import json, sys, urllib.request
body = (b"--demo\r\nContent-Disposition: form-data; name=\"image\"; filename=\"sample.jpg\"\r\n"
        b"Content-Type: application/octet-stream\r\n\r\n" + sys.stdin.buffer.read() + b"\r\n--demo--\r\n")
request = urllib.request.Request("http://127.0.0.1:8126/v1/eval/predict?track=service", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=demo"})
with urllib.request.urlopen(request, timeout=180) as response:
    result = json.load(response)
print("Model HTTP 200 | slug:", result.get("slug") or result.get("action"),
      "| inference:", result.get("timings_ms", {}).get("total_ms"), "ms")
' < "$photo"
  exit
fi
data_root=${1:-"$HOME/ml-data/brutforce/local-demo"}
mkdir -p "$data_root"
data_root=$(cd -- "$data_root" && pwd -P)
case "$data_root/" in "$root/"*) echo 'Data must live outside the clone' >&2; exit 1;; esac
if [[ $# -ge 2 ]]; then
  archives=$(cd -- "$2" && pwd -P)
  mode=offline
else
  archives="$data_root/archives"
  mkdir -p "$archives"
  mode=download
fi

for command in python3 docker curl openssl tar; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done
docker compose version >/dev/null

if [[ ! -f "$data_root/f8-bundle/onnx/vision.onnx" ||
      ! -f "$data_root/catalog-package/manifest.json" ||
      ! -d "$data_root/catalog-media" ||
      ! -f "$data_root/recommendations/index.json" ]]; then
  python3 "$root/scripts/bootstrap-assets.py" "$archives" "$mode" full
  tar -xf "$archives/01-recognition-data.tar.gz" -C "$data_root"
  cat "$archives"/02-recognition-weights.tar.part-00{0..5} | tar -xf - -C "$data_root"
  for name in 03-display-catalog.tar.gz 04-display-media.tar 05-text-recommendations.tar.gz; do
    tar -xf "$archives/$name" -C "$data_root"
  done
fi

if [[ ! -f "$root/deploy/.env.local" ]]; then
  sh "$root/scripts/docker-local.sh" init "$data_root"
else
  configured=$(python3 - "$root/deploy/.env.local" <<'PY'
import sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.startswith("ASSET_DIR="):
        print(line.partition("=")[2])
        break
PY
  )
  [[ "$configured" == "$data_root/f8-bundle" ]] || { echo 'Existing deploy/.env.local points to different data' >&2; exit 1; }
fi
if ! python3 - "$root/deploy/.env.local" <<'PY'
import sys
from pathlib import Path
sys.exit(not any(line.startswith("COMPOSE_PROJECT_NAME=") for line in Path(sys.argv[1]).read_text().splitlines()))
PY
then
  id=$(python3 - "$data_root" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])
PY
  )
  printf 'COMPOSE_PROJECT_NAME=brutforce-demo-%s\n' "$id" >> "$root/deploy/.env.local"
fi
sh "$root/scripts/docker-local.sh" up
sh "$root/scripts/docker-local.sh" smoke
echo 'Ready at http://127.0.0.1:8097/ — model photo: bash scripts/bootstrap-docker.sh photo /path/to/photo.jpg'
echo 'Stop: sh scripts/docker-local.sh stop'
