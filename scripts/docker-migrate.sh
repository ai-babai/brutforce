#!/bin/sh
set -eu
umask 077
pass=$(cat /run/secrets/db_password)
case "$pass" in *[!0-9a-f]*|'') echo 'db password must be nonempty lowercase hex' >&2; exit 1;; esac
export MIGRATION_DATABASE_URL="postgres://postgres:${pass}@postgres:5432/brutforce?sslmode=disable"
case "$CATALOG_VERSION" in *[!a-zA-Z0-9._-]*|'') echo 'unsafe catalog version' >&2; exit 1;; esac
cd /app
catalog-migrate
test -f /catalog-package/manifest.json || { echo 'approved catalog-release-1 package missing' >&2; exit 1; }
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -dry-run
snapshot="/snapshots/before-${CATALOG_VERSION}-$(date -u +%Y%m%dT%H%M%S%NZ)-$$.json"
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -snapshot-out "$snapshot"
echo "rollback snapshot: $snapshot"
catalog-import -package /catalog-package -media-root /catalog-media -version "$CATALOG_VERSION" -verify-db
