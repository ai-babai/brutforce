# Mobile wine behavior demo

Runnable React/Vite prototype derived from `design/wine-ux-atlas`. Recognition and catalog data are simulated and labeled in the interface.

## Run

```sh
npm install
npm run dev
```

Open http://127.0.0.1:5190. Vite proxies `/api` to http://localhost:8097.

The scan action requests a live outward-facing camera when the browser supports it. Native capture and gallery inputs remain available as fallbacks. JPEG, PNG, and GIF files up to 10 MiB are previewed locally, uploaded to the private photo endpoint, then referenced by `photoId` in the search request.

## Verify

```sh
npm test
npm run build
```

Behavior tests use Vitest with jsdom and mocked `fetch`; they do not require Playwright or a running backend. Stable screen IDs are `UI-001` through `UI-010`.

## API

- `GET /api/health`
- `POST /api/search` with `{ "scenario": "exact" | "uncertain" | "none" | "error", "query"?: string }`
- `POST /api/photos` as multipart form data with field `photo`; returns `{ "id", "createdAt", "bytes", "mime", "width", "height" }`
- `POST /api/search` also accepts optional `photoId` from the upload receipt.
- Response: `{ "demo": true, "candidates": [{ "id", "name", "winery", "year", "image", "description" }], "selectedId"?: string }`
