# Demo search API

Minimal, standard-library Go prototype for the Wine UX Atlas. It provides
predictable synthetic outcomes for frontend integration; it does not recognize
images or query a real wine catalog.

## Boundary and contract

**Producer:** this HTTP server. **Consumers:** the local demo frontend and
manual API clients. The canonical success-response schema is
[`contracts/demo-search.schema.json`](../../contracts/demo-search.schema.json).
This README defines endpoint behavior and error handling for the prototype.

`POST /api/search` accepts a JSON object no larger than 64 KiB:

```json
{"scenario":"exact","query":"каберне"}
```

`scenario` is optional and defaults to `exact`. Its allowed values are
`exact`, `uncertain`, `none`, and `error`. `query`, when supplied, must be a
string and filters candidate names and wineries with a case-insensitive
substring match. It is only meaningful for the default/exact flow.

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

The candidates are ordered Cabernet 2023, then Merlot 2022. `exact` returns
the matching candidates and selects the first one. `uncertain` returns both
candidates without `selectedId`; `none` returns an empty list; `error` returns
HTTP 503 and `{ "demo": true, "error": { "code", "message" } }`.
Invalid JSON/input/scenario returns HTTP 400. Unsupported methods return HTTP
405. Unknown `/api/...` paths return JSON HTTP 404. No compatibility promise is
made beyond this demo contract.

`GET /api/health` returns `{ "ok": true, "demo": true }`.

## Runtime

```sh
go run .
```

It listens on `127.0.0.1:8097`. Set `ADDRESS` to choose another listen address.
The server applies a 5-second header timeout, 10-second read/write timeouts,
and a 60-second idle timeout. Set `WEB_ROOT` to a frontend directory to serve
its static files and fall back to `index.html` for non-API routes. API routes
continue to return JSON errors.

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

Run: `go test -count=1 ./...`.
