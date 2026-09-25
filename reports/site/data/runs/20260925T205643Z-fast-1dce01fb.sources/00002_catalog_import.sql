-- +goose Up
-- Imported catalog records may legitimately have no stated vintage.  Extra
-- display fields live in JSONB so the small catalog table stays queryable.
ALTER TABLE demo_catalog ALTER COLUMN year DROP NOT NULL;
ALTER TABLE demo_catalog ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE catalog_versions (
    version TEXT PRIMARY KEY,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    package_sha256 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE catalog_state (
    singleton BOOLEAN PRIMARY KEY CHECK (singleton),
    version TEXT NOT NULL REFERENCES catalog_versions(version)
);

CREATE TABLE catalog_aliases (
    alias_slug TEXT PRIMARY KEY,
    canonical_slug TEXT NOT NULL REFERENCES demo_catalog(id)
);

-- +goose Down
-- Catalog snapshots are deliberately retained. Roll back an import with the
-- catalog-import restore command; schema migrations are never destructive.
SELECT 1;
