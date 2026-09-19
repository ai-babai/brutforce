# Demo search API

Minimal, standard-library Go prototype for the Wine UX Atlas. It provides
predictable synthetic outcomes for frontend integration; it does not recognize
images or query a real wine catalog. It can retain a private uploaded image for
the demo flow, but a stored receipt only gates the synthetic response.

## Embedded synthetic catalog

[`catalog.json`](catalog.json) is the read-only, embedded demo catalog. It has
eight synthetic red-dry wines with stable IDs; it is not a database, supplier
feed, or claim about real wine records. `GET /v1/catalog` returns its complete
ordered candidate list as `{ "demo": true, "candidates": [...] }`. The same
catalog is used by search, so catalog and search candidate IDs always match.

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
with the future contest endpoint are described in
[`contracts/api-versioning.md`](../../contracts/api-versioning.md).

`POST /v1/search` accepts a JSON object no larger than 64 KiB:

```json
{"scenario":"exact","query":"каберне"}
```

`scenario` is optional and defaults to `exact`. Its allowed values are
`exact`, `uncertain`, `none`, and `error`. `query`, when supplied, must be a
string and filters candidate names and wineries with a case-insensitive
substring match; a year string such as `"2023"` filters the same catalog. It is
only meaningful for the default/exact flow. `photoId`
is optional; when supplied, it must be an existing private upload receipt. It
does not enable image recognition.

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
is checked with `image.DecodeConfig`; accepted formats are JPEG, PNG, and GIF.
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
| API-015 | embedded catalog | eight unique stable synthetic records and matching `GET /v1/catalog` response |
| API-016 | name, winery, and year query | exact search filters the same embedded catalog and selects its first match |
| API-017 | documentation route or bundled asset | `GET /api/docs` and its local Swagger assets work; its own errors remain JSON API errors |
| API-018 | embedded OpenAPI and canonical schema | OpenAPI 3.1 documents exactly four implemented endpoint methods and the embedded schema matches the contract source |
| API-019 | versioned routes with `WEB_ROOT` configured | `/v1` business routes work; legacy business routes and unknown `/v1` paths are JSON 404, never SPA HTML |

Run: `go test -count=1 ./...`.

## Public input security
See [Security Specs](../../docs/product/security-spec.md) for input, upload concurrency/rate, storage and service resource limits. Search POST requires application/json and at most256 query characters. Uploads are decoded after dimension checks; originals remain private and untrusted.
