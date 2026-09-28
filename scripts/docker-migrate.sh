#!/bin/sh
set -eu
umask 077
pass=$(cat /run/secrets/db_password)
case "$pass" in *[!0-9a-f]*|'') echo 'db password must be nonempty lowercase hex' >&2; exit 1;; esac
export MIGRATION_DATABASE_URL="postgres://postgres:${pass}@postgres:5432/brutforce?sslmode=disable"
case "$CATALOG_VERSION" in *[!a-zA-Z0-9._-]*|'') echo 'unsafe catalog version' >&2; exit 1;; esac
cd /app
catalog-migrate -schema-only
test -f /catalog-package/manifest.json || { echo 'approved catalog-release-1 package missing' >&2; exit 1; }
snapshot="/snapshots/before-${CATALOG_VERSION}-$(date -u +%Y%m%dT%H%M%S%NZ)-$$.json"
catalog-import -export-snapshot "$snapshot"
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -previous-snapshot "$snapshot" -dry-run -report-out /snapshots/catalog-dryrun.json
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -snapshot-out "$snapshot"
echo "pre-import snapshot (empty on first install): $snapshot"
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -previous-snapshot "$snapshot" -verify-db
