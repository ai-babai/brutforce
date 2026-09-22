# Настоящий каталог · BE-045 (согласовано Максом через Sigma Ops)

Package v2: #44, private server public/SCHEMA.md. Full dataset/images stay out of Git.
App projection: apps/api/internal/catalogmodel/wine.go (API JSON tags authoritative).
Unknown year/volume omitted, SQL year NULL. Internal Go zero is never serialized.
SourceURL distinguishes real catalog from synthetic fixtures; recognition remains reference/demo.
Image paths become `/media/catalog/<400|800|original>/<sha256>.webp`; immutable registered root.
No path supplied by clients is used as arbitrary filesystem access.

Runtime packages use `/srv/lct/data/catalog/releases/<version>/` with flat
`wines.jsonl`, `aliases.json`, `catalog.json`, `manifest.json`, and
`internal/display-policy.json`. Shared immutable media uses
`/srv/lct/data/catalog/media/{400,800,original}/<sha256>.webp` and is served as
`/media/catalog/<role>/<sha256>.webp`; release/internal files are not web roots.
Manifest `schema_version` is `catalog-release-1` and includes `catalog_version`,
`files:[{path,sha256,bytes}]`, and
`media:[{path,sha256,bytes,width,height,mime_type}]`. Hashes cover exact bytes.

GET /v2/catalog?limit=24&cursor=…&q=… → {demo:boolean,candidates:Wine[],nextCursor?:string,catalogVersion:string}.
Default24, max60; q searches whole catalog (name/producer/year), NOT loaded browser page.
Stable canonical ID order; slug may change without changing identity. Cursor is bound to query and catalog version; stale→409,
invalid→400; no missing/duplicate canonical IDs within one version. Aliases not listed.
GET /v2/catalog/{slug} → {demo:boolean,candidate:Wine,canonicalId:string} resolves aliases.
Missing→404 JSON. Catalog response demo describes catalog provenance, not ML validity.
Recognition responses retain separate demo/modelVersion reference markings.

Database: catalog_items(id PK, slug UNIQUE, name, winery, year nullable, image,
description, display_order, metadata JSONB holding Wine extras).
catalog_versions(version PK, package_sha256, imported_at), catalog_state(singleton boolean PK, version),
catalog_aliases(alias_slug PK,canonical_slug REFERENCES catalog_items(slug)).
The forward migration preserves IDs and leaves a temporary demo_catalog compatibility view.
package_sha256 stores the exact manifest SHA for runtime releases; legacy snapshots use a projection digest.
Importer and API coordinate exact SQL in migration. Catalog snapshot atomic on import;
old snapshot export/restore required for rollback, never destructive reset/down.
Migration/seed must not reinsert demo records into imported real catalog.
Assets stay files outside DB. Import validates package paths (no traversal/symlink),
checksums/dimensions/type/bytes and alias references before DB mutation.
Dry-run validates and reports counts without mutations; repeat import same package idempotent.

`catalog-import --package DIR --media-root ROOT --version V --dry-run
--previous-snapshot SNAPSHOT --report-out FILE --validator-version HASH` emits schemaVersion 1,
kind `catalog-data-quality`, status, catalogVersion, manifestSHA256,
validatorVersion, timestamps/duration, counts, and DQ001..DQ008 plus DQ011 cases.
Every case has id, title, section, status, summary, and failures. Required
missing/skipped/error/failed cases block acceptance. DQ009 target-DB and DQ010
target-HTTP evidence are recorded only after placement, separately from preflight.
Unexpected removed IDs block DQ011 until the exact set is authorized; the initial
demo-to-real transition is authorized only for the existing eight demo IDs.

DQ006 proves decoded dimensions, bounds and geometry against the prepared master.
It does not prove that a master or upstream source photo was never cropped.
DQ007 proves the agreed suppression policy and structural metadata constraints;
it does not decide whether the organizer photographed the correct wine.
Source reconciliation and image preparation remain separately recorded in the package's
PREPARATION.md and source-manifest reference. The runtime materializer copies accepted bytes
and metadata; it neither guesses missing values nor re-encodes images. Its small fixtures verify this.

A release candidate binds app artifact/Git SHA, exact catalog manifest SHA, and
model version/mode. Changing data creates a new candidate without rebuilding the
app or inheriting PROD approval. An unchanged manifest may reuse a full report
only with the same validator version and immutable byte verification; the UI
shows the original report time. TEST follows automatically after all required
preflight gates pass. PROD requires explicit human approval of the exact candidate.
