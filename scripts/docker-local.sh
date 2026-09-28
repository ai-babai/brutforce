#!/bin/sh
# Local/clean-Linux Compose commands. Does not act on Sigma's systemd services.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
envfile=${DOCKER_ENV_FILE:-"$root/deploy/.env.local"}
if [ "${1:-}" = init ]; then
  data_root=${2:-"$HOME/brutforce-local"}
  test -d "$data_root/f8-bundle" && test -d "$data_root/catalog-package" &&
    test -d "$data_root/catalog-media" && test -f "$data_root/recommendations/index.json" || {
      echo 'Extract the data archives into DATA_ROOT before init' >&2; exit 1;
    }
  data_root=$(CDPATH= cd -- "$data_root" && pwd -P)
  test ! -e "$envfile" || { echo "Environment file already exists: $envfile" >&2; exit 1; }
  (umask 077
    mkdir -p "$data_root/secrets"
    chmod 700 "$data_root/secrets"
    for name in db_password app_password; do
      test -e "$data_root/secrets/$name" || openssl rand -hex 32 > "$data_root/secrets/$name"
    done
    while IFS= read -r line; do
      case $line in
        ASSET_DIR=*) printf 'ASSET_DIR=%s/f8-bundle\n' "$data_root" ;;
        CATALOG_PACKAGE_DIR=*) printf 'CATALOG_PACKAGE_DIR=%s/catalog-package\n' "$data_root" ;;
        CATALOG_MEDIA_DIR=*) printf 'CATALOG_MEDIA_DIR=%s/catalog-media\n' "$data_root" ;;
        RECOMMENDATION_INDEX_FILE=*) printf 'RECOMMENDATION_INDEX_FILE=%s/recommendations/index.json\n' "$data_root" ;;
        SECRETS_DIR=*) printf 'SECRETS_DIR=%s/secrets\n' "$data_root" ;;
        *) printf '%s\n' "$line" ;;
      esac
    done < "$root/deploy/docker.env.example" > "$envfile"
  )
  echo "Local configuration written to $envfile"
  exit 0
fi
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
  *) echo 'usage: scripts/docker-local.sh init [DATA_ROOT]|preflight|up|smoke|stop|down' >&2; exit 64 ;;
esac
