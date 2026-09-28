# Самостоятельный запуск BrutForce

[Главная](../README.md) · [Архитектура](../ARCHITECTURE.md) · [Операции нашей команды](../deploy/PIPELINE.md)

Обе команды ниже запускают код **на своей машине**, без доступа к TEST/PROD, токена команды или её серверов. Минимальный режим работает с файлами репозитория. Полный режим требует право на данные и отдельный проверенный комплект; сейчас репозиторий его не раздаёт. Оба режима открывают интерфейс и API на `http://127.0.0.1:8097/`.

| | Минимальный | Полный |
|---|---|---|
| Инструменты | Go 1.23, Node.js 22, npm **или** Docker Engine + Compose v2 | Linux x86-64, Docker Engine + Compose v2, Python 3.11+, `curl`, `openssl`; для ручного пути также Go 1.23, Node.js 22, PostgreSQL 18 и Python 3.12 |
| Данные | Не нужны: восемь демонстрационных записей из `apps/api/catalog.json` | Bundle распознавания, пакет каталога, media и отдельный индекс рекомендаций, размещённые вне Git |
| Фото | Приватная загрузка; поиск в демонстрационном каталоге **не** распознаёт вино | Настоящее ранжирование по изображению и проверка slug по каталогу организаторов |
| Проверка | `/v1/health`, `/v2/catalog?limit=1` | `preflight`, `smoke`, известное разрешённое фото и точный slug |

Демо не содержит PostgreSQL, модели и конкурсных данных. `POST /v1/eval/predict` в нём возвращает 503 `recognition_unavailable`, а не выдуманный slug.

## Минимальный режим без Docker

Из корня клона на macOS или Linux:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run build
mkdir -p local-uploads
cd apps/api
UPLOAD_DIR="$(pwd)/../../local-uploads" WEB_ROOT="$(pwd)/../web/dist" go run .
```

Откройте <http://127.0.0.1:8097/>. Во втором терминале: `curl --fail http://127.0.0.1:8097/v1/health` и `curl --fail 'http://127.0.0.1:8097/v2/catalog?limit=1'`. Остановка — Ctrl-C. `local-uploads/` исключён из Git; загруженные фотографии сохраняются до удаления владельцем.

Для разработки интерфейса вместо сборки можно запустить `npm --prefix apps/web run dev` во втором терминале и открыть <http://127.0.0.1:5190/>; API должен работать в первом.

## Минимальный режим с Docker

Из корня клона на машине с Docker Engine и Compose v2:

```sh
docker compose -f deploy/compose.demo.yaml up --build -d --wait
curl --fail http://127.0.0.1:8097/v1/health
docker compose -f deploy/compose.demo.yaml down
```

Откройте <http://127.0.0.1:8097/> до `down`. Профиль собирает фронтенд и API в один образ и хранит загруженные фотографии в отдельном Docker volume `brutforce-demo_uploads`. `down` без `-v` сохраняет volume; `docker compose -f deploy/compose.demo.yaml up -d --wait` запускает его снова. Другие сервисы и внешние данные не требуются.

## Данные для полного режима

Структура на своей Linux-машине **вне** клона (пути в примерах подставьте абсолютные):

```text
~/brutforce-local/
  f8-bundle/                    # overlay/, parent/, onnx/, index/, catalog/, models/hub/, ocr/
  catalog-package/              # manifest.json, wines.jsonl, aliases.json, catalog.json, internal/
  catalog-media/                # 400/, 800/, original/ — <sha256>.webp
  recommendations/index.json   # отдельный индекс витрины, не visual-neighbors из bundle
  secrets/db_password           # только для полного Compose
  secrets/app_password          # только для полного Compose
```

`catalog-package/manifest.json` имеет `schema_version: catalog-release-1`, `catalog_version` и списки файлов/media с SHA-256, размерами и типом изображения — [схема и контракт импорта](../contracts/catalog-display.md). `f8-bundle/` — имя каталога зафиксированной CPU-сборки распознавателя, а не отдельная технология, которую нужно устанавливать. Он содержит 50 файлов с зафиксированными именами и хешами из [манифеста](../deploy/assets/f8-cpu.sha256): код сервиса, веса детектора и визуального энкодера, индекс эталонов, OCR-данные и список slug организаторов. [Опись компонентов и происхождение](../deploy/assets/INVENTORY.md). Веса, датасет и индексы не размещайте в Git или Docker build context.

Если у вас **уже есть разрешённые источники** в семи каталогах, `scripts/asset-bundle.py export` собирает точный bundle. Карта путей — JSON с ключами `overlay`, `parent`, `onnx`, `index`, `catalog`, `models`, `ocr`; значения — абсолютные каталоги источников (для `models` корень HF `hub/`). Например:

```json
{"overlay":"/data/overlay","parent":"/data/parent","onnx":"/data/onnx","index":"/data/index","catalog":"/data/catalog","models":"/data/hf/hub","ocr":"/data/tessdata"}
```

Сохраните карту как `/private/source-map.json`, затем из корня клона:

```sh
python3 scripts/asset-bundle.py export --sources /private/source-map.json --out /private/f8-bundle
python3 scripts/asset-bundle.py verify /private/f8-bundle
```

`export` не скачивает данные и не перезаписывает существующий каталог: каждый входной файл уже должен совпадать с SHA. Для полученного готового bundle нужен только `verify`. Каталожный пакет, media и рекомендации передаются/готовятся **отдельно**; код подготовки своих данных и проверка пакета — [контракт импортёра](../contracts/catalog-display.md) и [CLI в apps/api](../apps/api/README.md#be-045-реальный-каталог). Не подменяйте точный индекс рекомендаций визуальными соседями модели: это разные форматы и задачи.

### Состояние полного комплекта

Для зафиксированного в примере профиля нет общедоступного URL на **все** четыре части и не подтверждены права на их распространение. Образцы публичных весов из [описи](../deploy/assets/INVENTORY.md) не заменяют производный индекс, код, каталог и media. Поэтому посторонний читатель может сейчас самостоятельно запустить минимальный режим и проверить форматы/команды, **но не восстановить полный поиск из одного этого репозитория**. Запуск полного Compose на чистом Linux с известным ответом также не подтверждён; подробности в [результатах](SOLUTION.md#воспроизведение-и-ограничения). Никакого токена нашей команды не требуется для API: доступность и права на данные — отдельный нерешённый вопрос.

## Полный режим с Docker

Этот профиль запускает PostgreSQL 18, одноразовые миграцию/импорт, CPU-сервис компьютерного зрения и веб-приложение. Предварительные условия: Linux x86-64, Docker Engine с Compose v2, Python 3.11+ для проверки файлов, `curl`, `openssl`, комплект выше и память под модель (лимит vision-контейнера — 7 GiB; минимальный объём RAM хоста не измерен).

```sh
DATA_ROOT="$HOME/brutforce-local"
mkdir -p "$DATA_ROOT/secrets"
DATA_ROOT=$(realpath "$DATA_ROOT")
umask 077
openssl rand -hex 32 > "$DATA_ROOT/secrets/db_password"
openssl rand -hex 32 > "$DATA_ROOT/secrets/app_password"
cp deploy/docker.env.example deploy/.env.local
```

Создавайте пароли **один раз** на новой базе; права каталога `secrets` — 0700, файлов — 0600. В `deploy/.env.local` замените пять путей `ASSET_DIR`, `CATALOG_PACKAGE_DIR`, `CATALOG_MEDIA_DIR`, `RECOMMENDATION_INDEX_FILE` (именно файл) и `SECRETS_DIR` на абсолютные пути под полученным `$DATA_ROOT`; значения env-файла не раскрывают пароли. Для **другого** согласованного набора данных должны одновременно совпадать `CATALOG_VERSION`, manifest SHA в `scripts/docker-local.sh` и `RECOMMENDATION_INDEX_SHA256` — изменение только одной строки недостаточно.

```sh
sh scripts/docker-local.sh preflight
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
curl --fail-with-body --max-time 10 -F 'image=@/path/to/approved-sample.jpg' \
  http://127.0.0.1:8097/v1/eval/predict
sh scripts/docker-local.sh stop
```

`preflight` проверяет 50 SHA bundle, точные manifest/index SHA, наличие secrets и Compose-конфигурацию. `up` строит образы, применяет миграции/импорт и ждёт готовности. `smoke` проверяет health и каталог, **не** точность модели: известное разрешённое фото должно дать HTTP 200 и `{"slug":"точный-slug"}`. `stop` сохраняет volumes; `down` снимает контейнеры/сеть без удаления volumes. Скрипт рассчитан на один закреплённый комплект — произвольные файлы или другую версию каталога он не примет.

## Полный режим без Docker

Это ручная сборка компонентов, **не подтверждённая end-to-end на чистом Linux**. Используйте её только с тем же проверенным комплектом; без него конкурсный API остаётся недоступен. Зависимости: PostgreSQL 18, Go 1.23, Node.js 22, Python 3.12, Tesseract с русским/английским OCR и пакеты из [vision-requirements.txt](../deploy/assets/vision-requirements.txt). За примером настройки PostgreSQL и разделения роли миграций/чтения смотрите [контракт БД](../contracts/database.md). Порядок запуска и переменные соответствуют [Compose](../deploy/compose.yaml), [vision bridge](../scripts/docker-vision-bridge.py) и [migrate](../scripts/docker-migrate.sh):

1. Проверить bundle командой `python3 scripts/asset-bundle.py verify /absolute/f8-bundle`; установить Python-зависимости в собственное окружение и предоставить `models/hub`, `onnx/`, `ocr/`, `parent/` через `HF_HOME`, `NIGHT_SO_ONNX_DIR`, `TESSDATA_PREFIX`, `F0_BASE_CODE_DIR` и `PYTHONPATH`. Путь к словарю OCR задаёт `F8_OCR_LEXICON_SPEC`.
2. Запустить `/absolute/f8-bundle/overlay/night_server.py` с `--catalog /absolute/f8-bundle/catalog/catalog-bundle.json --index-dir /absolute/f8-bundle/index --host 127.0.0.1 --port 8126 --threads 6 --encoder so400m --route onnx640`; дождаться `/healthz`.
3. Настроить свою БД: `MIGRATION_DATABASE_URL` для миграции/импорта, отдельный `DATABASE_URL` для HTTP; из `apps/api/` выполнить `go run ./cmd/catalog-migrate`, затем `go run ./cmd/catalog-import -package /absolute/catalog-package -media-root /absolute/catalog-media -version VERSION -dry-run` и, после принятого отчёта, ту же команду с `-snapshot-out /private/before.json` вместо `-dry-run`.
4. Собрать UI: `npm --prefix apps/web ci && npm --prefix apps/web run build`. Для Go API задать `WEB_ROOT` на `apps/web/dist`, `UPLOAD_DIR` вне web root, `VISION_SERVICE_URL=http://127.0.0.1:8126`, `VISION_CATALOG_VERSION`, `VISION_INDEX_VERSION`, `VISION_SLUGS_FILE`, `VISION_SLUGS_SHA256`, `RECOMMENDATION_INDEX_FILE` и `RECOMMENDATION_INDEX_SHA256` из **того же** согласованного комплекта, затем запустить `go run .` из `apps/api/`. Доступ к `/media/catalog/…` требует отдельно настроенного файлового HTTP-сервера для разрешённых WebP; Compose включает его готовую реализацию в `web-proxy`.

Ручная установка не эквивалентна подтверждённому Compose-выпуску: пока не проверены совпадение OCR-версии, права на данные и полный прогон с известным фото. Если вам нужен повторяемый полный путь, используйте Compose с согласованным комплектом, а не смешивайте его версии.
