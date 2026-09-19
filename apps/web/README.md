# Mobile wine behavior demo

Runnable React/Vite prototype derived from `design/wine-ux-atlas`. Recognition and catalog data are simulated and labeled in the interface.

## Run

```sh
npm install
npm run dev
```

Open http://127.0.0.1:5190. Vite proxies `/api` to http://localhost:8097.

On a phone, the file input requests the outward-facing camera through `capture="environment"`. Desktop browsers and some mobile browsers may show a file picker instead; this is a browser/device limitation. The chosen image is previewed locally and is not uploaded by this demo.

## Verify

```sh
npm test
npm run build
```

Behavior tests use Vitest with jsdom and mocked `fetch`; they do not require Playwright or a running backend. Stable screen IDs are `UI-001` through `UI-010`.

## API

- `GET /api/health`
- `POST /api/search` with `{ "scenario": "exact" | "uncertain" | "none" | "error", "query"?: string }`
- Response: `{ "demo": true, "candidates": [{ "id", "name", "winery", "year", "image", "description" }], "selectedId"?: string }`
