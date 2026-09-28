# BrutForce

Team repository for the **LCT 2026** competition. Given a Russian wine-label photo, we look up an existing catalog card. Team members: Maxim Popkov (`ai-babai`) and Roman (`@MisterMolox`). [Русский README](README.md).

[Prototype](https://app.dzap.pw) · [Run with the model](#run-with-the-model) · [Local demo](#quick-start) · [Results and limitations](docs/SOLUTION.md)

**Submission links**

- **Repository:** [ai-babai/brutforce](https://github.com/ai-babai/brutforce) — private; reviewer access needs verification.
- **Documentation:** [documentation entry](docs/README.md) — in the same repository.
- **Presentation:** link pending file and rights approval.
- **Prototype:** [app.dzap.pw](https://app.dzap.pw).

## Run with the model

You need Linux x86-64, Docker Engine with Compose v2, Python 3.11+, `curl`, `openssl`, and enough memory for the model and catalog. The [full runbook (Russian)](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8) covers acquisition, verification, password setup and data retention; [English entry](docs/RUNBOOK.en.md).

Obtain **four separate parts** through the team's approved channel: the verified F8 bundle, display catalog package, catalog media, and exact recommendation-index file. If you have no access, contact Maxim Popkov (`ai-babai`) or Roman (`@MisterMolox`); there is no download URL. `preflight` stops without the exact recommendation file. Another index cannot replace it.

Put the received parts **outside the clone**. Set an absolute root on your Linux host:

```sh
DATA_ROOT="$HOME/brutforce-local"
mkdir -p "$DATA_ROOT"
DATA_ROOT=$(realpath "$DATA_ROOT")
```

Layout under `$DATA_ROOT`:

```text
f8-bundle/
catalog-package/manifest.json
catalog-media/
recommendations/index.json
secrets/db_password
secrets/app_password
```

On first setup, copy the example from the clone root: `cp deploy/docker.env.example deploy/.env.local`. In `deploy/.env.local`, enter **expanded absolute paths** with the resulting `$DATA_ROOT` prefix, not a literal `$DATA_ROOT`:

- `ASSET_DIR` → `f8-bundle/`; `CATALOG_PACKAGE_DIR` → `catalog-package/`.
- `CATALOG_MEDIA_DIR` → `catalog-media/`; `RECOMMENDATION_INDEX_FILE` → `recommendations/index.json` (a **file**).
- `SECRETS_DIR` → `secrets/` with two password files created as in the [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8). Keep the pinned `CATALOG_VERSION` and `RECOMMENDATION_INDEX_SHA256` from the example.

Once the parts are in place, from the clone root:

```sh
sh scripts/docker-local.sh preflight
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
API=http://127.0.0.1:8097
curl --fail-with-body --max-time 10 \
  -F "image=@/path/to/approved.jpg" \
  "$API/v1/eval/predict"
sh scripts/docker-local.sh stop
```

`preflight` checks the bundle, catalog, index, secrets and Compose. `up` waits for healthy services; `smoke` checks HTTP health and the catalog. Use an approved photo with a known answer: expect HTTP 200 and the same nonempty `slug`. `stop` preserves data. See [current Compose and asset limitations](docs/SOLUTION.md#воспроизведение-и-ограничения).

## Quick start

This is a **synthetic local demo** without label recognition. Install Go 1.23, Node.js 22 and npm; PostgreSQL is not needed. Open two terminals at the clone root.

First:

```sh
mkdir -p ./local-uploads
cd apps/api
UPLOAD_DIR="$(pwd)/../../local-uploads" \
  go run .
```

Second (from the clone root again):

```sh
cd apps/web
npm ci
npm run dev
```

Open <http://127.0.0.1:5190/> and check the API with `curl --fail http://127.0.0.1:8097/v1/health`. Stop both processes with Ctrl-C. Only the owner should remove photos in `local-uploads/`. The demo contest endpoint returns `503 recognition_unavailable`.

## How it works

1. The mobile React UI accepts a photo or text query.
2. The Go API stores uploaded photos privately and reads cards from PostgreSQL.
3. A separate CPU service detects the label, compares visual features, and uses text when needed to rank slugs.
4. The Go API verifies the slug and shows an existing card when the display catalog contains it. Contest [`POST /v1/eval/predict`](contracts/eval-predict.md) accepts `image` and returns a slug.
5. A separate pinned index suggests related cards from display text and winery attributes; it does not replace recognition. [Full architecture](ARCHITECTURE.md).

Measurements, versions and check boundaries are in [results](docs/SOLUTION.md). [Project map](MAP.md) · [Contracts](contracts/README.md) · [Release and rollback](deploy/PIPELINE.md). The repository remains private; no team code license has been agreed and third-party rights require separate checks.
