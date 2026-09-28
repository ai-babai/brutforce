# BrutForce

**A wine-label photo → an existing Russian wine catalog card.** Mobile React/TypeScript UI, Go API, and a separate CPU vision service. [Русский README](README.md).

[Try TEST](https://test.ops.dzap.pw) · [Quick start](#quick-start) · [Architecture](ARCHITECTURE.md) · [Results](docs/SOLUTION.md) · [Presentation: pending](docs/SOLUTION.md#презентация-и-права) · [Agent guide](AGENTS.md)

As of 28 September 2026, TEST runs F8 CPU (app baseline `d26afa3`, candidate `b0428147`). [app.dzap.pw](https://app.dzap.pw) still serves a placeholder; do not infer a production ML release. A verified, rights-cleared UI screenshot and presentation URL are pending.

## For reviewers

The TEST contest endpoint is `POST https://test.ops.dzap.pw/v1/eval/predict` with multipart field `image`. On an exact match it returns one `slug`; see the [contract](contracts/eval-predict.md). TEST availability is not a production acceptance result. See the [architecture](ARCHITECTURE.md), [measured results and caveats](docs/SOLUTION.md), and the [single operational runbook (Russian)](docs/RUNBOOK.ru.md) with an [English entry](docs/RUNBOOK.en.md). A release tag has not been confirmed.

## Quick start

This local mode uses **synthetic demo data, not F8 recognition**. Install Go 1.23, Node.js 22 and npm; it does not require PostgreSQL. From the repository root, in terminal 1:

```sh
mkdir -p ./local-uploads
cd apps/api
UPLOAD_DIR="$(pwd)/../../local-uploads" go run .
```

From the repository root, in terminal 2:

```sh
cd apps/web
npm ci
npm run dev
```

Open <http://127.0.0.1:5190/> and check `curl --fail http://127.0.0.1:8097/v1/health`. Stop both processes with Ctrl-C. Without F8 the contest endpoint intentionally returns `503 recognition_unavailable`. Do not publish uploaded photos. For a **real F8 CPU** setup, obtain the pinned external assets and follow the [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8); access and clean Linux reproducibility remain to be verified.

```text
React UI → Go API ──→ PostgreSQL display catalog
              ├──→ private uploads and feedback
              └──→ F8 CPU service → pinned vision assets outside Git
```

Historical TEST smoke on a preceding app candidate (`86c8d38`) returned 3/3 valid slugs in 5.301 / 4.812 / 3.626 seconds. It does **not** establish accuracy or p95 for current TEST, let alone PROD. See [results](docs/SOLUTION.md) for the distinct DEV comparison. Visual alternatives are not exact matches or taste predictions.

[Project map](MAP.md) · [API contracts](contracts/README.md) · [Release pipeline](deploy/PIPELINE.md). No team code license has yet been agreed; third-party images, catalog data and model weights require separate permission.
