# Search and contest API

Go API for the Wine UX Atlas. Without a configured vision service, the local
demo uses predictable synthetic outcomes. With `VISION_SERVICE_URL` and an
imported display catalog, a private photo receipt feeds real ranked search and
the contest endpoint returns the top organizer-verified slug. The display
catalog is loaded by a separately validated importer.

## Synthetic catalog: PostgreSQL and standalone mode

[`catalog.json`](catalog.json) defines eight synthetic red-dry wines with stable IDs.
With DATABASE_URL set, catalog and search read PostgreSQL; without it, the embedded
fixture serves standalone tests. A configured database failure never falls back to
embedded data. These default records are not a supplier feed. `GET /v2/catalog`
returns bounded pages (default 24, maximum 60), with `catalogVersion` and optional
`nextCursor`. All manual text searches use its `q` parameter. Real display records
may be imported separately; see [catalog-display.md](../../contracts/catalog-display.md).
The default photo/reference engine remains synthetic and is unavailable against
an incompatible real catalog rather than inventing a match.

Only the established Cabernet has the existing concept-bottle image. Merlot
intentionally has an empty `image` field so the client can show its missing
image state. The six new records point to explicitly synthetic bottle SVGs.

## Boundary and contract

**Producer:** this HTTP server. **Consumers:** the local demo frontend and
manual API clients. The canonical success-response schema is
[`contracts/demo-search.schema.json`](../../contracts/demo-search.schema.json).
This README defines endpoint behavior and error handling for the prototype.
Interactive local documentation is available at `GET /api/docs`; it serves the
OpenAPI 3.1 document at `GET /api/openapi.json` and its canonical search schema
at `GET /api/schema/demo-search.schema.json`. API versioning and the boundary
with the contest endpoint are described in
[`contracts/api-versioning.md`](../../contracts/api-versioning.md).

## Contest adapter

`POST /v1/eval/predict` is a separate, stateless contest boundary documented
by [`contracts/eval-predict.md`](../../contracts/eval-predict.md). It accepts
one bounded multipart `image`, detects JPEG/PNG/GIF/WebP from bytes rather than
the filename, and returns only `{ "slug": "..." }` when an injected
recognizer returns a nonempty exact slug. It never uses `UPLOAD_DIR`, the
synthetic catalog, or the demo search result.

Without `VISION_SERVICE_URL`, a valid decoded image returns JSON HTTP 503
`recognition_unavailable`. With the vision service configured, the same
ranked result powers the contest slug and real-catalog photo search; see
[`contracts/vision-serving.md`](../../contracts/vision-serving.md).
`EVAL_MAX_CONCURRENT` controls this route's independent concurrency cap
(default 4). Run its contract checks with
`go test -count=1 -run '^TestEVAL' ./...`. They prove the HTTP boundary and
the stub hand-off only, not recognition quality.

`POST /v1/search` accepts a JSON object no larger than 64 KiB:

```json
{"scenario":"exact","query":"каберне"}
```

`scenario` is optional and defaults to `exact`. Its allowed values are
`exact`, `uncertain`, `none`, and `error`. `query`, when supplied, must be a
string. In the local catalog fallback it uses the lightweight token search
specified in [catalog-display.md](../../contracts/catalog-display.md): normalized
names/producer/year, word prefixes and one bounded typo; numeric tokens are exact.
It is only meaningful for the default/exact flow. `photoId`
is optional; when supplied, it must be an existing private upload receipt.
With a real display catalog and configured vision service, that receipt sends
the stored original to ranked image recognition. The synthetic local mode
keeps the receipt-gated demo behavior.

Successful responses have this shape:

```json
{
  "demo": true,
  "candidates": [
    {
      "id": "demo-cabernet-sauvignon-2023",
      "name": "Каберне Совиньон",
      "winery": "Демо-винодельня",
      "year": 2023,
      "image": "/assets/concept-bottle.png",
      "description": "Синтетическая карточка DEMO для макета."
    }
  ],
  "selectedId": "demo-cabernet-sauvignon-2023"
}
```

The catalog begins Cabernet 2023, then Merlot 2022. `exact` returns matching
candidates and selects the first one. `uncertain` returns the first two catalog
candidates without `selectedId`; `none` returns an empty list; `error` returns
HTTP 503 and `{ "demo": true, "error": { "code", "message" } }`.
Invalid JSON/input/scenario returns HTTP 400. Unsupported methods return HTTP
405. Unknown `/v1/...` paths return JSON HTTP 404. The old business routes
`/api/health`, `/api/catalog`, `/api/photos`, and `/api/search` also return
JSON HTTP 404; they are not aliases. No compatibility promise is made beyond
this demo contract.

`GET /v1/health` returns `{ "ok": true, "demo": true }`.

## Private upload receipt

`POST /v1/photos` accepts `multipart/form-data` with exactly one required
`photo` file field. Its content, not the client filename or declared MIME type,
is checked with `image.DecodeConfig`; accepted formats are JPEG, PNG, GIF,
and WebP, regardless of filename or declared MIME type.
The photo content limit is 10 MiB and the default pixel limit is 25,000,000.

On success it returns HTTP 201:

```json
{
  "id": "32-lowercase-hex-characters",
  "createdAt": "2026-09-19T12:00:00.000000000Z",
  "bytes": 12345,
  "mime": "image/png",
  "width": 1200,
  "height": 1600
}
```

`id` is generated with `crypto/rand`. The original bytes and JSON receipt are
stored as private files outside `WEB_ROOT`; the receipt metadata is the commit
marker, so a partially written original is never a valid `photoId`. There is no
public upload list or download route. Files are written with mode `0600` in an
`UPLOAD_DIR` directory set to mode `0700`. Request filenames and photo content
are never logged.

`UPLOAD_DIR` is mandatory for uploads. If it is missing or unusable, uploads
return HTTP 503 `storage_unavailable`. `UPLOAD_MAX_BYTES` bounds all regular
files in that directory; its default is 209715200 bytes (200 MiB). The service
does not delete existing images automatically; a full budget returns HTTP 503
`storage_full`. `UPLOAD_MAX_PIXELS` optionally replaces the 25,000,000-pixel
default. Invalid/oversize/non-image uploads return HTTP 400.

The upload directory is separate from the embedded read-only `catalog.json`:
the former contains private user photos and receipts, while the latter contains
only versioned synthetic demo records. Neither has a public file route.

`POST /v1/search` with an unknown valid-format `photoId` returns HTTP 404
`photo_not_found`; a malformed ID returns HTTP 400 `invalid_photo_id`.

## Runtime

```sh
go run .
```

It listens on `127.0.0.1:8097`. Set `ADDRESS` to choose another listen address.
The server applies a 5-second header timeout, 10-second read/write timeouts,
and a 60-second idle timeout. Set `WEB_ROOT` to a frontend directory to serve
its static files and fall back to `index.html` for non-API routes. API routes
continue to return JSON errors. Set `UPLOAD_DIR` to an absolute private path
outside `WEB_ROOT` to enable uploads; configure service write permissions for
that directory before deployment.

## Behavior specs

The permanent `httptest` specs are intentionally fast and do not claim search
quality:

| ID | Input / condition | Expected observation |
| --- | --- | --- |
| API-001 | exact | ordered synthetic candidates, with Cabernet 2023 selected |
| API-002 | uncertain | both synthetic candidates, no selection |
| API-003 | none | successful empty candidate list |
| API-004 | error | HTTP 503 structured demo error |
| API-005 | `query: "мерло"` | case-insensitive manual filtering selects Merlot 2022 |
| API-006 | malformed or invalid scenario | HTTP 400 structured error |
| API-007 | wrong method and unknown API route | JSON HTTP 405 and 404 |
| API-008 | health | HTTP 200 demo health response |
| API-009 | `WEB_ROOT` static file and client route | serves the file and falls back to `index.html` |
| API-010 | valid PNG multipart upload | stores matching private bytes and metadata receipt; receipt works in search |
| API-011 | invalid or oversized upload | HTTP 400 and no accepted receipt |
| API-012 | upload without `UPLOAD_DIR` | HTTP 503 `storage_unavailable` |
| API-013 | unknown valid-format `photoId` | HTTP 404 `photo_not_found` |
| API-014 | configured storage budget exhausted | HTTP 503 `storage_full` |
| API-015 | embedded catalog | eight unique stable synthetic records and matching `GET /v2/catalog` response |
| API-016 | name, winery, and year query | exact search filters the same embedded catalog and selects its first match |
| API-017 | documentation route or bundled asset | `GET /api/docs` and its local Swagger assets work; its own errors remain JSON API errors |
| API-018 | embedded OpenAPI and canonical schema | OpenAPI 3.1 documents the demo endpoints plus the separately defined contest adapter; the embedded schema matches the contract source |
| API-019 | versioned routes with `WEB_ROOT` configured | `/v1` business routes work; legacy business routes and unknown `/v1` paths are JSON 404, never SPA HTML |

Run: `go test -count=1 ./...`.

## Public input security
See [Security Specs](../../docs/product/security-spec.md) for input, upload concurrency/rate, storage and service resource limits. Search POST requires application/json and at most256 query characters. Uploads are decoded after dimension checks; originals remain private and untrusted.

## PostgreSQL operations (BE-031)

Contract: [database.md](../../contracts/database.md). Schema/seed: `migrations/`.
From `apps/api`, migrate explicitly with migration-role credentials already in
`MIGRATION_DATABASE_URL`: `go run ./cmd/catalog-migrate`. In a packaged release,
run `./catalog-migrate` with `migrations/` beside it and that directory as cwd.
Goose applies schema once; explicit seed reruns preserve existing rows (`ON CONFLICT DO NOTHING`).
Never run schema changes under the HTTP runtime role. Startup with DATABASE_URL
requires a reachable DB; query errors return HTTP503 catalog_unavailable without secrets.
The health route is process liveness, not a database readiness check.

Fast suite: `go test -count=1 ./...` (no DB required). SQL integration is build-tagged:
`lct-db-test maks bash -c 'cd /path/to/apps/api && go test -tags=integration -count=1 -run "^TestDB00[1-5]" .'`.
The wrapper resets only the registered test schema and supplies both credentials.
Missing credentials or an unexpected database fail the integration tests, not skip them.
For measuring just DB work, precompile `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go test -c -tags=integration -o db-tests .`,
copy it and migrations/, then run with `go tool test2json -t -p brutforce-behavior-demo/apps/api ./db-tests
-test.v=test2json -test.run '^TestDB00[1-5]' -test.count=1` inside the wrapper.
No real images or competition data are needed for these tests.

## Сервис Романа: поиск и рекомендации (BE-032)

Контракт, бюджеты и ошибки: [wine-services.md](../../contracts/wine-services.md).
Машинная спецификация: [OpenAPI](../../contracts/wine-services.openapi.json).
Запуск референса и передача Роману: [ROMAN-SERVICES.md](../../docs/agent-guide/ROMAN-SERVICES.md).

`SEARCH_SERVICE_URL` и `RECOMMENDATION_SERVICE_URL` задаются отдельно; допустим один адрес.
`CATALOG_VERSION=demo-v1` связывает ответ с текущим синтетическим каталогом.
Настроенный сервис не заменяется симулятором при сбое. Без URL поиска сохраняется прежний
синтетический режим; без URL рекомендаций новая ручка возвращает503.
`POST /v1/recommendations` принимает `{"wineId":"demo-cabernet-sauvignon-2023","limit":3}`.
Публичный API дополняет ID полями каталога, сохраняя порядок сервиса.
Конкурсный endpoint отдельно; эталон не подключается к нему автоматически.

## BE-045: реальный каталог

Постраничная выдача: `GET /v2/catalog?limit=24&q=…&cursor=…`; карточка/alias:
`GET /v2/catalog/{slug}`. Старый `/v1/catalog` возвращает JSON404.
См. [контракт](../../contracts/catalog-display.md) и [BDD](../../docs/product/catalog-display-spec.md).

Офлайн-проверка пакета (без подключения БД):
```sh
go run ./cmd/catalog-import -package /path/to/package -version catalog-display-20260922-v2 -dry-run
```

Импорт после отдельного согласования: применить миграции, сделать snapshot через
`catalog-import -package … -version … -snapshot-out /private/path/before.json`
с migration-role; assets разместить как `CATALOG_ASSET_ROOT/<version>/images/*`.
Секреты только environment-file, не CLI-аргументы/логи. Snapshot содержит каталожные
данные, сохраняется вне Git. Обратное переключение: `catalog-import -restore …`.
Пакет v2 содержит public/wines.json и public/aliases.json; пустые/невалидные связи
останавливают импорт до записи. Повтор версии с другим содержимым отклоняется.

Миграция допускает SQL NULL года и защищает импортированный каталог от demo-seed.
Файлы версионируются и остаются вне БД; не удалять старые assets при rollback.
Reference-движок несовместим с реальными IDs. Фото-поиск реального каталога
доступен только через `VISION_SERVICE_URL`; `VISION_CATALOG_VERSION` и
`VISION_INDEX_VERSION` закрепляют версии ответа распознавателя.
`VISION_SLUGS_FILE` и `VISION_SLUGS_SHA256` закрепляют точный список slug
конкурсного каталога вне Git. Ранжированные slug сопоставляются с ID
существующих карточек витрины, если карточка доступна. Без vision-сервиса фото
возвращает явную ошибку. Поиск по названию работает через локальный каталог.
Рекомендации остаются отдельным сервисом и не подменяются кандидатами поиска.
