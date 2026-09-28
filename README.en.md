# BrutForce — Russian wine-label scanner

Built for the **Digital Transformation Leaders 2026** challenge from the Svoe Vino platform. The task is to identify an exact Russian wine catalog entry from a label photo and show its card on a phone. The system combines image retrieval, a catalog and a mobile web application; it does not label an unrelated card as an exact match.

**Project authors:** Maxim Popkov ([Telegram @skifmax](https://t.me/skifmax)) and Roman Karandashov ([GitHub MisterMolox](https://github.com/MisterMolox)). [Русский README](README.md).

[Try the app](https://app.dzap.pw) · [Self-hosting guide (Russian)](docs/SELF-HOST.ru.md) · [Download data](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ) · [Architecture](ARCHITECTURE.md) · [Evidence and limits](docs/SOLUTION.md)

## Start without external data

With Docker Engine and Compose v2 installed, run:

```sh
git clone https://github.com/ai-babai/brutforce.git
cd brutforce
docker compose -f deploy/compose.demo.yaml up --build -d --wait
```

Open <http://127.0.0.1:8097/>. This is a demo with eight sample cards, text search and photo upload, **without wine recognition**. The contest endpoint returns 503 in this mode. Stop with `docker compose -f deploy/compose.demo.yaml down`; see the [non-Docker option](docs/SELF-HOST.ru.md#минимальный-режим-без-docker) or [full deployment](docs/SELF-HOST.ru.md#полный-режим-с-docker).

For full mode, [download all 14 files](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ), verify SHA-256 and stream-extract the six weight-archive parts as shown in the [transfer guide (Russian)](docs/ASSET-TRANSFER.ru.md#как-восстановить-на-linux). Then, from the repository root:

```sh
sh scripts/docker-local.sh init "$HOME/brutforce-local"
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
```

`up` includes preflight checks. CPU recognition **source code is in [apps/vision/](apps/vision/README.md)**; data and weights are external to Git. Public access to the files does not establish redistribution rights for models, catalog data or photos. See [host requirements and verification limits](docs/SELF-HOST.ru.md#полный-режим-с-docker).

## Architecture at a glance

```text
Browser (React) --> Go API --> PostgreSQL (display cards)
                        |----> Python CPU (model + reference index) --> slug
                        `----> recommendation index (separate from the model)
Contest client --> POST /v1/eval/predict --> Go API --> validated slug
```

The organizer sends multipart `image` and reads `{"slug":"..."}`; the app uses `/v1/photos` followed by `/v1/search` with a `photoId`. A recognized organizer slug without a matching display card is not replaced by an unrelated wine. See the [full architecture](ARCHITECTURE.md), [external data layout](docs/SELF-HOST.ru.md#данные-для-полного-режима) and [API contract](contracts/eval-predict.md).

[Repository](https://github.com/ai-babai/brutforce) · [documentation index](docs/README.md). A presentation URL is not confirmed; distribution rights for third-party data and weights require separate approval.
