# BrutForce

**A wine-label photo → an existing Russian wine catalog card.** Mobile React/TypeScript UI, Go API, and a separate CPU vision service. [Русский README](README.md).

[Try the live app](https://app.dzap.pw) · [Quick start](#quick-start) · [Docker CPU F8](#docker-with-real-f8-cpu) · [Architecture](ARCHITECTURE.md) · [Results](docs/SOLUTION.md) · [Presentation: pending](docs/SOLUTION.md#презентация-и-права) · [Agent guide](AGENTS.md)

As of 28 September 2026, [app.dzap.pw](https://app.dzap.pw) runs F8 CPU (app `d26afa3`, candidate `b0428147…`, catalog `svoe-20260927-alpha-2035-v1`, recommendations SHA `f05f16c7…`). Public HTTPS, a real photo, and the product HTTP flow passed smoke checks. Browser UI/device-camera review, a rights-cleared screenshot, and a presentation URL remain pending.

## For reviewers

The PROD contest endpoint is `POST https://app.dzap.pw/v1/eval/predict` with multipart field `image`. A successful response returns one `slug`; see the [contract](contracts/eval-predict.md). Three sample responses do not establish accuracy. See the [architecture](ARCHITECTURE.md), [measured results and caveats](docs/SOLUTION.md), and the [single operational runbook (Russian)](docs/RUNBOOK.ru.md) with an [English entry](docs/RUNBOOK.en.md). A release tag has not been confirmed.

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

## Docker with real F8 CPU

On Linux x86-64 with Docker Engine/Compose v2, obtain the rights-cleared F8 bundle ([50-file SHA manifest](deploy/assets/f8-cpu.sha256)), approved display catalog package and media, and pinned recommendation index **outside Git**. Copy [`deploy/docker.env.example`](deploy/docker.env.example) to `deploy/.env.local` and set absolute paths to those assets and a private `SECRETS_DIR` containing separate `db_password` and `app_password` files. The [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8) explains bundle verification/export, permissions and data retention; the [English entry](docs/RUNBOOK.en.md) points to the same commands.

```sh
sh scripts/docker-local.sh preflight
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
sh scripts/docker-local.sh stop
```

The stack contains PostgreSQL, a one-shot migration/import, vision and web/API bound to `127.0.0.1:8097`. HTTP smoke is not a known-answer model test. Image builds, external asset delivery and clean-Linux/OCR parity are still pending; live PROD runs under systemd, not Docker.

```text
React UI → Go API ──→ PostgreSQL display catalog
              ├──→ private uploads and feedback
              └──→ F8 CPU service → pinned vision assets outside Git
```

PROD smoke on `d26afa3` returned 3/3 nonempty slugs in 4.595 / 4.354 / 3.079 seconds; the first known answer matched. This does **not** establish official-gold accuracy or p95. See [results](docs/SOLUTION.md) for the distinct DEV comparison. Alternatives are not exact matches or taste predictions; live recommendations use the pinned display-text/attributes/winery index.

[Project map](MAP.md) · [API contracts](contracts/README.md) · [Release pipeline](deploy/PIPELINE.md). No team code license has yet been agreed; third-party images, catalog data and model weights require separate permission.
