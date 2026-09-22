# Настоящий каталог · BE-045 (согласовано Максом через Sigma Ops)

Package v2: #44, private server public/SCHEMA.md. Full dataset/images stay out of Git.
App projection: apps/api/internal/catalogmodel/wine.go (API JSON tags authoritative).
Unknown year/volume omitted, SQL year NULL. Internal Go zero is never serialized.
SourceURL distinguishes real catalog from synthetic fixtures; recognition remains reference/demo.
Image paths become `/catalog-assets/<version>/<package-relative-path>`; immutable registered root.
No path supplied by clients is used as arbitrary filesystem access.

GET /v2/catalog?limit=24&cursor=…&q=… → {demo:boolean,candidates:Wine[],nextCursor?:string,catalogVersion:string}.
Default24, max60; q searches whole catalog (name/producer/year), NOT loaded browser page.
Stable canonical slug order. Cursor opaque, bound to query and catalog version; stale→409,
invalid→400; no missing/duplicate canonical IDs within one version. Aliases not listed.
GET /v2/catalog/{slug} → {demo:boolean,candidate:Wine,canonicalId:string} resolves aliases.
Missing→404 JSON. Catalog response demo describes catalog provenance, not ML validity.
Recognition responses retain separate demo/modelVersion reference markings.

Database migration: demo_catalog year nullable, metadata JSONB holding Wine extras;
catalog_versions(version PK, imported_at), catalog_state(singleton boolean PK, version),
catalog_aliases(alias_slug PK,canonical_slug REFERENCES demo_catalog(id)).
Importer and API coordinate exact SQL in migration. Catalog snapshot atomic on import;
old snapshot export/restore required for rollback, never destructive reset/down.
Migration/seed must not reinsert demo records into imported real catalog.
Assets stay files outside DB. Import validates package paths (no traversal/symlink),
checksums/dimensions/type/bytes and alias references before DB mutation.
Dry-run validates and reports counts without mutations; repeat import same package idempotent.
