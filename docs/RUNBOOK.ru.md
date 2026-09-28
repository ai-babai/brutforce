# Запуск и обслуживание · 28.09.2026

Этот документ — операционная памятка команды по закреплённому комплекту и серверным выпускам. Внешнему читателю для первого запуска нужен [самостоятельный маршрут](SELF-HOST.ru.md) (минимальный режим без данных, Docker и полный профиль). [English entry](RUNBOOK.en.md) и [выпуск/откат PROD](../deploy/PIPELINE.md) — отдельные ссылки.

Скрипты и SHA-манифест 50 файлов есть в репозитории. Передача внешних assets и запуск на чистом Linux ожидают проверки.

## Предварительные условия

- Локальное синтетическое демо: Go 1.23, Node.js 22, npm; любая поддерживаемая ими ОС. Без базы и весов. Храните реальные фото в непубличной папке.
- Реальный F8 CPU: Linux x86-64, Docker Engine и Compose v2, Python 3.11+, `curl`, `openssl`, память для модели и индекса. Минимальный объём памяти на чистом Linux не установлен. Перед оценкой дождитесь readiness: прежняя проба холодной загрузки заняла 15,453 с.
- Внешние assets: код F8 с parent imports, веса и детектор, SO400M и препроцессинг, OCR-лексикон, индекс и metadata, slug allowlist, mapping витрины, media каталога и отдельный индекс рекомендаций. [f8-runtime.json](../deploy/f8-runtime.json) фиксирует лишь часть связки.

## Локальное демо без ML

Для первого запуска выполните [команды минимального режима](SELF-HOST.ru.md#минимальный-режим-без-docker). `curl --fail http://127.0.0.1:8097/v1/health` проверяет только liveness; в демо `POST /v1/eval/predict` отвечает 503. Остановите процесс Ctrl-C. Папку `local-uploads/` игнорирует Git; её содержимое удаляет только владелец данных.

Быстрые локальные проверки (после установки npm-зависимостей):

```sh
cd apps/api && go test -count=1 ./...
cd ../web && npm test && npm run build
```

Из корня также доступен `node scripts/run-fast-checks.mjs`: он записывает историю быстрых проверок UI/API. Для SQL-интеграции нужны выделенный тестовый PostgreSQL и разные runtime/migration credentials; [правила БД](../contracts/database.md). Миграции выполняют только на своей тестовой БД.

## Полный CPU-профиль F8

Попросите Максима Попкова (`ai-babai`) или Романа (`@MisterMolox`) передать через согласованный канал четыре части: F8 bundle, пакет каталога, media каталога и **точный файл** индекса рекомендаций. Веса, код F8 и данные отсутствуют в clone. Локальный bundle у Repro прошёл сверку 50/50 SHA; это пока не канал передачи эксперту. Сверьте выданный F8 bundle с [50 SHA](../deploy/assets/f8-cpu.sha256), а остальные части — с закреплёнными версиями и хешами через `preflight`. При отсутствии exact recommendation index прекратите настройку: visual-neighbors в F8 bundle не подходят.

Инструменты уже в Git: [экспорт и проверка bundle](../scripts/asset-bundle.py), [Compose](../deploy/compose.yaml), [пример env](../deploy/docker.env.example), [CLI запуска](../scripts/docker-local.sh). Не заменяйте недостающие assets похожими файлами.

Если bundle ещё нужно собрать, оператор задаёт вне Git JSON-карту семи групп `overlay`, `parent`, `onnx`, `index`, `catalog`, `models`, `ocr`. Значения — каталоги-источники. `export` сверяет каждый файл с SHA-манифестом, собирает bundle и проверяет его снова. Для готового bundle достаточно `verify`:

```sh
python3 scripts/asset-bundle.py export --sources /absolute/path/to/operator-sources.json --out /absolute/path/to/new-f8-bundle
python3 scripts/asset-bundle.py verify /absolute/path/to/new-f8-bundle
```

`export` не перезаписывает существующий `--out`. Группа `models` указывает на корень HF hub; в bundle это `models/hub/…`. Все пути выше — примеры абсолютных путей вне репозитория, их заменяет оператор.

[Каталожный пакет](../contracts/catalog-display.md), media и индекс рекомендаций передаются отдельно от bundle. Действующий TEST/PROD индекс рекомендаций имеет SHA `f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f`: он опирается на текст витрины и атрибуты винодельни. Visual-neighbors в F8 bundle не заменяют его.

После получения четырёх частей разместите их **вне клона**. Пример каталога на Linux (выполните в терминале запуска):

```sh
DATA_ROOT="$HOME/brutforce-local"
mkdir -p "$DATA_ROOT"
DATA_ROOT=$(realpath "$DATA_ROOT")
```

Под этим корнем должны быть разные `f8-bundle/` (50 файлов), `catalog-package/` (с `manifest.json`), `catalog-media/`, `recommendations/index.json` (один точный файл) и `secrets/` (два файла паролей). Реальное расположение может отличаться; перенесите в `.env.local` развёрнутые абсолютные пути, а не литерал `$DATA_ROOT`.

После получения и размещения частей выполните из корня клона на Linux x86-64:

1. Создайте приватный `SECRETS_DIR` вне репозитория (права 0700). В нём должны лежать два разных файла `db_password` и `app_password`, каждый с непустой lowercase hex строкой и правами 0600. Например, на машине запуска (только если этот каталог новый):

   ```sh
   umask 077
   mkdir -p "$DATA_ROOT/secrets"
   chmod 0700 "$DATA_ROOT/secrets"
   openssl rand -hex 32 > "$DATA_ROOT/secrets/db_password"
   openssl rand -hex 32 > "$DATA_ROOT/secrets/app_password"
   ```

   Подставьте развернутый абсолютный путь этого каталога **вне клона** в `SECRETS_DIR` (не литерал `$HOME`). Не печатайте значения и не помещайте их в аргументы команд, Docker layers или Actions artifacts. Не запускайте этот блок повторно на сохранённой БД: пароли перестанут совпадать с созданной ролью.
2. При первой настройке `cp deploy/docker.env.example deploy/.env.local`. Впишите абсолютные пути: `ASSET_DIR` → `f8-bundle/`, `CATALOG_PACKAGE_DIR` → `catalog-package/`, `CATALOG_MEDIA_DIR` → `catalog-media/`, `RECOMMENDATION_INDEX_FILE` → `recommendations/index.json` (**файл**), `SECRETS_DIR` → `secrets/`. Все пять путей начинаются с развёрнутого `$DATA_ROOT`. Сохраните закреплённые `CATALOG_VERSION` и `RECOMMENDATION_INDEX_SHA256`, пока владелец не выдаст согласованный комплект. `.env.local` исключён из Git; пароли хранятся только в файлах из шага 1.
3. Выполните команды ниже. `preflight` проверяет 50 SHA, каталожный manifest, файл рекомендаций, секреты и Compose. `up` строит образы, мигрирует локальную БД, импортирует каталог и ждёт healthy vision/web. `smoke` проверяет HTTP health/catalog.

```sh
sh scripts/docker-local.sh preflight
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
```

Сервис доступен на `http://127.0.0.1:8097` машины запуска. После `smoke` выполните контрольный запрос ниже с **разрешённым фото и известным slug**, затем проверьте `POST /v1/photos` → `POST /v1/search` → карточку.

Для остановки выполните `sh scripts/docker-local.sh stop`. Команда `sh scripts/docker-local.sh down` удаляет контейнеры и сеть **без `-v`**: БД, uploads, feedback и snapshots остаются в volumes. Повторный `up` использует их снова. Для смены версии каталога заранее подготовьте миграцию и восстановление; `docker compose down -v` удалит сохранённые данные.

Синтаксис скриптов и `docker compose config` проверены. Repro собрал оба linux/amd64-образа на OrbStack; исправление web-сборки вошло в приватный `main` через PR #105. Catalog/media прошли dry-run DQ001–008, DQ011 требует baseline; импорт не выполнялся. Exact index рекомендаций пока не передан, поэтому полный Compose не запускался. Чистый Linux и known-answer через Compose остаются открытыми. Tesseract 5.3 в образе не равен серверному 5.5: OCR parity ожидает проверки. Работающий [PROD](https://app.dzap.pw) запущен через systemd.

Контрольный конкурсный запрос к **уже работающему реальному** API с разрешённым локальным фото (не использовать в демо без F8):

```sh
curl --fail-with-body --max-time 10 -F "image=@/path/to/approved-sample.jpg" http://127.0.0.1:8097/v1/eval/predict
```

Ожидается HTTP 200/201 и JSON с непустым `slug`, равным известному ответу для фото. Один ответ подтверждает этот случай, общая accuracy требует отдельного набора. В приложении `POST /v1/photos` принимает поле `photo`, а `POST /v1/search` — JSON с `photoId`; [контракт](../contracts/vision-serving.md). Личные фото не передают в PR и логи.

## Обновление, PROD и откат

Доступны TEST <https://test.ops.dzap.pw> и [PROD](https://app.dzap.pw): app `d26afa3`, candidate `b0428147…`, CPU F8, выпуск 28 сентября 2026. Назначенный оператор сверяет release archive, каталог, модель, mapping, индекс рекомендаций и policy по [PIPELINE](../deploy/PIPELINE.md). Данные, uploads и credentials PROD отделены от TEST.

Первый откат возвращает прежнюю страницу, сохраняет данные и не останавливает общий vision. SQL schema автоматически не откатывается. Серверные пути и права оператора нужны только назначенному оператору.
