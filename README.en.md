# BrutForce — Russian wine-label scanner

Built for the **Digital Transformation Leaders 2026** challenge from the Svoe Vino platform. The task is to identify an exact Russian wine catalog entry from a label photo and show its card on a phone. The system combines image retrieval, a catalog and a mobile web application; it does not label an unrelated card as an exact match.

**Team:** Maxim Popkov ([Telegram @skifmax](https://t.me/skifmax)) and Roman Karandashov ([GitHub MisterMolox](https://github.com/MisterMolox)). [Русский README](README.md).

[Try the app](https://app.dzap.pw) · [Run it yourself (Russian guide)](docs/SELF-HOST.ru.md) · [Architecture](ARCHITECTURE.md) · [Evidence and limits](docs/SOLUTION.md)

## Start without external data

With Go 1.23 and Node.js 22 installed, run from the repository root on macOS or Linux:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run build
mkdir -p local-uploads
cd apps/api
UPLOAD_DIR="$(pwd)/../../local-uploads" WEB_ROOT="$(pwd)/../web/dist" go run .
```

Open <http://127.0.0.1:8097/>. This is an explicit synthetic demo: eight sample cards, text search and private photo upload, **no wine recognition**. The contest endpoint returns 503 in this mode. For Docker, run `docker compose -f deploy/compose.demo.yaml up --build -d --wait` from the repository root; `docker compose -f deploy/compose.demo.yaml down` stops it without deleting the uploads volume. No team token is needed.

The [self-hosting guide](docs/SELF-HOST.ru.md) distinguishes this demo from the full mode, gives hardware/software requirements, file layout, data verification, Docker commands and the non-Docker component map. The full mode requires a separately obtained model/code bundle, visual index, catalog package/media and recommendation index. Those bytes are not in Git; there is **no independent public download for the complete pinned bundle yet**, and clean-Linux parity is unverified. Hash manifests check bytes after acquisition but cannot provide them. A team-issued token is not required for the app; access to licensed data remains an open dependency.

The React UI is in `apps/web/`, the Go API and PostgreSQL adapter in `apps/api/`, the full Compose profile in `deploy/compose.yaml`, and the model asset verifier in `scripts/asset-bundle.py`. The organizer sends one multipart `image` to `POST /v1/eval/predict` and reads a single `{"slug":"..."}`; the application uses `/v1/photos` followed by `/v1/search` with a `photoId`. See [architecture](ARCHITECTURE.md) and [API contract](contracts/eval-predict.md).

[Repository](https://github.com/ai-babai/brutforce) is currently private and access is granted separately. A presentation URL is not confirmed. Code licensing and redistribution rights for third-party data and weights are not yet settled. [Documentation index](docs/README.md) · [Team operations](deploy/PIPELINE.md).
