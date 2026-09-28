# BrutForce — Russian wine-label scanner

Built for the **Digital Transformation Leaders 2026** challenge from the Svoe Vino platform. The task is to identify an exact Russian wine catalog entry from a label photo and show its card on a phone. The system combines image retrieval, a catalog and a mobile web application; it does not label an unrelated card as an exact match.

**Project authors:** Maxim Popkov ([Telegram @skifmax](https://t.me/skifmax)) and Roman Karandashov ([GitHub MisterMolox](https://github.com/MisterMolox)). [Русский README](README.md).

[Try the app](https://app.dzap.pw) · [Run it yourself (Russian guide)](docs/SELF-HOST.ru.md) · [Architecture](ARCHITECTURE.md) · [Evidence and limits](docs/SOLUTION.md)

## Start without external data

With Docker Engine and Compose v2 installed, run:

```sh
git clone https://github.com/ai-babai/brutforce.git
cd brutforce
docker compose -f deploy/compose.demo.yaml up --build -d --wait
```

Open <http://127.0.0.1:8097/>. This is a demo with eight sample cards, text search and photo upload, **without wine recognition**. The contest endpoint returns 503 in this mode. Stop with `docker compose -f deploy/compose.demo.yaml down`; see the [non-Docker option](docs/SELF-HOST.ru.md#минимальный-режим-без-docker) or [full deployment](docs/SELF-HOST.ru.md#полный-режим-с-docker).

The [self-hosting guide](docs/SELF-HOST.ru.md) covers both modes, requirements and deployment. CPU recognition **source code is in [apps/vision/](apps/vision/README.md)**. Full mode separately needs weights, visual index, catalog package/media and recommendation index. These data are not in Git and **do not have a public download URL yet**. The full stack started and passed health/catalog smoke checks on a Mac running linux/amd64 containers; independent clean-Linux and known-photo checks are still outstanding.

## Modules and data map

```text
brutforce/                          REPOSITORY: code, no large data
|-- apps/web/                        React/TypeScript mobile UI
|-- apps/api/                        Go API: uploads, search, cards, recommendations
|   `-- migrations/                  PostgreSQL schema for display cards
|-- apps/vision/                     Python CPU recognition source
|   |-- overlay/, parent/            Pinned serving modules
|   `-- overlay/spec/lexicon.json    OCR confirmation policy
|-- deploy/compose.demo.yaml         UI + API demo without DB or model
|-- deploy/compose.yaml              Full web, vision, migrate and postgres stack
|-- scripts/docker-local.sh          Full Compose preflight and startup
`-- contracts/                       API and data formats

~/brutforce-local/                   EXTERNAL DATA: required for full mode
|-- f8-bundle/                        Recognition DATA and organizer catalog
|   |-- onnx/, models/hub/, ocr/      Model weights, processor, OCR languages
|   |-- index/index.npz              Reference-photo vectors (NOT display WebP)
|   |-- catalog/catalog-bundle.json  Organizer slugs and reference metadata
|   `-- overlay/organizer-slugs.json Allowed organizer slugs for Go API
|-- catalog-package/                 2,038 display cards, manifest and aliases
|-- catalog-media/{400,800,original}/ Display-card WebP images
|-- recommendations/index.json       Text/attribute card neighbors, NOT image vectors
`-- secrets/                          Locally generated DB and app passwords
```

After obtaining and extracting the data archives, run `sh scripts/docker-local.sh init "$HOME/brutforce-local"` to generate local configuration and passwords, then `sh scripts/docker-local.sh up` to start the full stack. See the [transfer and index-rebuild guide](docs/ASSET-TRANSFER.ru.md) and [deployment requirements](docs/SELF-HOST.ru.md#полный-режим-с-docker). The organizer sends multipart `image` to `POST /v1/eval/predict` and reads `{"slug":"..."}`; the application uses `/v1/photos` followed by `/v1/search` with a `photoId`. See [architecture](ARCHITECTURE.md) and [API contract](contracts/eval-predict.md).

[Repository](https://github.com/ai-babai/brutforce) · [documentation index](docs/README.md). A presentation URL is not confirmed; distribution rights for third-party data and weights require separate approval.
