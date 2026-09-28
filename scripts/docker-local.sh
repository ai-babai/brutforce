#!/bin/sh
# Local/clean-Linux Compose commands. Does not act on Sigma's systemd services.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
envfile=${DOCKER_ENV_FILE:-"$root/deploy/.env.local"}
test -f "$envfile" || { echo 'Set DOCKER_ENV_FILE to a private copy of deploy/docker.env.example' >&2; exit 1; }
set -a
. "$envfile"
set +a
compose() { docker compose --env-file "$envfile" -f "$root/deploy/compose.yaml" "$@"; }
preflight() {
  python3 "$root/scripts/asset-bundle.py" verify "$ASSET_DIR"
  python3 - "$RECOMMENDATION_INDEX_FILE" "$RECOMMENDATION_INDEX_SHA256" <<'PY'
import hashlib,sys
with open(sys.argv[1], 'rb') as f:
    got=hashlib.file_digest(f,'sha256').hexdigest()
if got != sys.argv[2]:
    sys.exit('recommendation index SHA mismatch')
print('recommendation index SHA verified:', got)
PY
  test -f "$CATALOG_PACKAGE_DIR/manifest.json"
  python3 - "$CATALOG_PACKAGE_DIR/manifest.json" <<'PY'
import hashlib,sys
with open(sys.argv[1], 'rb') as f:
    got=hashlib.file_digest(f,'sha256').hexdigest()
if got != 'd88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef':
    sys.exit('catalog release manifest SHA mismatch')
print('catalog release manifest SHA verified:', got)
PY
  test -d "$CATALOG_MEDIA_DIR"
  test -s "$SECRETS_DIR/db_password" && test -s "$SECRETS_DIR/app_password"
  compose config --quiet
}
case ${1:-} in
  preflight) preflight ;;
  up) preflight; compose build web migrate vision; compose up -d --wait ;;
  smoke)
    curl --fail --show-error --silent http://127.0.0.1:8097/readyz -o /dev/null
    curl --fail --show-error --silent http://127.0.0.1:8097/v2/catalog?limit=1 -o /dev/null
    curl --fail --show-error --silent http://127.0.0.1:8097/v1/health
    ;;
  stop) compose stop ;;
  down) compose down ;; # no -v: DB, uploads, feedback and snapshots survive
  *) echo 'usage: scripts/docker-local.sh preflight|up|smoke|stop|down' >&2; exit 64 ;;
esac
