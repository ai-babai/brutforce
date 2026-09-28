# BrutForce

Given a wine-label photo, BrutForce looks up an existing Russian wine catalog card. It has a mobile UI; the live prototype uses a CPU recognition service. [Русский README](README.md).

[Try the live prototype](https://app.dzap.pw) · [Quick demo start](#quick-start) · [How it works](ARCHITECTURE.md) · [Results and limits](docs/SOLUTION.md)

**Four submission links**

- **Repository:** [ai-babai/brutforce](https://github.com/ai-babai/brutforce) — private; reviewer access needs verification.
- **Documentation:** [documentation entry](docs/README.md) — in the same private repository.
- **Presentation:** link pending file and rights approval.
- **Prototype:** [app.dzap.pw](https://app.dzap.pw) — live.

## Quick start

This is a **synthetic local demo** without label recognition. Install Go 1.23, Node.js 22 and npm; no database is needed. For the real model, obtain external assets and follow the [step-by-step runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8). From the repository root, in terminal 1:

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

Open <http://127.0.0.1:5190/> and check the API with `curl --fail http://127.0.0.1:8097/v1/health`. Stop both processes with Ctrl-C. Only the data owner should remove `local-uploads/`; do not publish uploaded photos. The demo contest endpoint returns `503 recognition_unavailable`.

## Real setup and results

On Linux x86-64 with Docker Engine/Compose v2, obtain the F8 bundle, catalog package and media, and separate recommendation index from the owner **outside Git**. The [runbook (Russian)](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8) covers acquisition, configuration, verification, startup and shutdown; the [English entry](docs/RUNBOOK.en.md) points to those steps. The [50-file SHA manifest](deploy/assets/f8-cpu.sha256) pins the model bundle. Asset delivery, image builds and clean-Linux startup remain unverified. Live PROD runs under systemd.

As of 28 September 2026, TEST and [PROD](https://app.dzap.pw) use F8 CPU: app `d26afa3`, candidate `b0428147…`, catalog `svoe-20260927-alpha-2035-v1`, recommendation index `f05f16c7…`. Documentation first entered private `main` at `b451ecd`; its SHA may be newer and does not identify deployed code. See [architecture and version boundaries](ARCHITECTURE.md).

On PROD, the original participant script returned a nonempty `slug` for **3 of 3** sample photos in **4.595 / 4.354 / 3.079 s**; the first known answer matched. This is HTTP smoke, not an overall accuracy or p95 result. The specification's 90–100% and <3 s are targets; other measurements and limitations are in [results](docs/SOLUTION.md). Browser UI and the physical camera remain unverified.

```text
React UI → Go API ──→ PostgreSQL display catalog
              ├──→ private uploads and feedback
              └──→ F8 CPU service → pinned vision assets outside Git
```

The contest `POST /v1/eval/predict` accepts multipart `image` and returns a verified slug ([contract](contracts/eval-predict.md)). The app maps it to a catalog card. A separate pinned display-text/attributes/winery index recommends cards; it does not predict taste.

[Project map](MAP.md) · [API contracts](contracts/README.md) · [Web UI](apps/web/) · [Go API](apps/api/) · [Release pipeline](deploy/PIPELINE.md) · [Documentation](docs/README.md). Fast checks: `go test -count=1 ./...` from `apps/api`, `npm test` from `apps/web`; the [report index](reports/README.md) lists broader checks.

The repository remains **PRIVATE**; reviewer access needs verification. No team code license has been agreed; rights to design references, catalog data, datasets and weights require separate checks. [Details](docs/SOLUTION.md#презентация-и-права).
