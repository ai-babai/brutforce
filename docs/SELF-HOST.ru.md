# Самостоятельный запуск BrutForce

[Главная](../README.md) · [Архитектура](../ARCHITECTURE.md) · [Данные для переноса](ASSET-TRANSFER.ru.md)

Оба режима запускают код **на своей машине**, без доступа к TEST/PROD, токена команды или её серверов. Минимальный режим работает с файлами репозитория. Для полного режима [комплект данных доступен отдельно](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ), но права на дальнейшее распространение моделей, каталога и фотографий не установлены. Интерфейс и API открываются на `http://127.0.0.1:8097/`.

| | Минимальный | Полный |
|---|---|---|
| Инструменты | Go 1.23, Node.js 22, npm **или** Docker Engine + Compose v2 | Linux x86-64, Docker Engine + Compose v2, Python 3.11+, GNU `sha256sum`, `tar`, `curl`, `openssl`; для ручного пути также Go 1.23, Node.js 22, PostgreSQL 18 и Python 3.12 |
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

Скачайте **все 14 файлов** из [папки комплекта](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ): пять обычных архивов, шесть частей `02-recognition-weights.tar.part-000` … `005`, `README.ru.md`, `02-recognition-weights.tar.sha256` и `SHA256SUMS`. Части архива весов нельзя распаковывать по отдельности; [точные команды проверки SHA-256 и потоковой распаковки](ASSET-TRANSFER.ru.md#как-восстановить-на-linux) находятся в одном месте. В Git данные не входят.

Структура на своей Linux-машине **вне** клона (пути в примерах подставьте абсолютные):

```text
~/brutforce-local/
  f8-bundle/                    # данные: overlay/, onnx/, index/, catalog/, models/hub/, ocr/
  catalog-package/              # manifest.json, wines.jsonl, aliases.json, catalog.json, internal/
  catalog-media/                # 400/, 800/, original/ — <sha256>.webp
  recommendations/index.json   # отдельный индекс витрины, не visual-neighbors из bundle
  secrets/db_password           # только для полного Compose
  secrets/app_password          # только для полного Compose
```

`catalog-package/manifest.json` имеет `schema_version: catalog-release-1`, `catalog_version` и списки файлов/media с SHA-256, размерами и типом изображения — [схема и контракт импорта](../contracts/catalog-display.md). `f8-bundle/` содержит **32 файла данных** с зафиксированными именами и хешами из [манифеста](../deploy/assets/f8-cpu.sha256): веса детектора и визуального энкодера, индекс эталонов, OCR-данные и список slug организаторов. [Исходный CPU-код и OCR-правила](../apps/vision/README.md) лежат в Git и копируются в Docker-образ при сборке, в архиве их нет. [Опись компонентов и происхождение](../deploy/assets/INVENTORY.md). Веса, датасет и индексы не размещайте в Git или Docker build context.

**Свои данные:** если речь о фотографиях для проверки, отправляйте их multipart-полем `image` в [конкурсный API](../contracts/eval-predict.md), не копируйте в `f8-bundle/`. Если речь о замене эталонов или каталога вин, текущий Compose **не принимает произвольную папку**: индекс, список допустимых slug, каталог витрины, media, рекомендации и закреплённые SHA/версии должны соответствовать друг другу. [Контракт пакета каталога](../contracts/catalog-display.md) описывает импорт; [пересборка визуального индекса](ASSET-TRANSFER.ru.md#визуальный-индекс-по-эталонным-изображениям-организаторов) требует исходные reference WebP и checkpoint, которых нет в опубликованном комплекте. Для первого запуска используйте готовые согласованные данные выше.

Если у вас **уже есть разрешённые источники** в шести каталогах, `scripts/asset-bundle.py export` собирает bundle **без Python-кода**. Карта путей — JSON с ключами `overlay`, `onnx`, `index`, `catalog`, `models`, `ocr`; значения — абсолютные каталоги источников (для `models` корень HF `hub/`, для `overlay` только slug и визуальный snapshot). Например:

```json
{"overlay":"/data/overlay","onnx":"/data/onnx","index":"/data/index","catalog":"/data/catalog","models":"/data/hf/hub","ocr":"/data/tessdata"}
```

Сохраните карту как `/private/source-map.json`, затем из корня клона:

```sh
python3 scripts/asset-bundle.py export --sources /private/source-map.json --out /private/f8-bundle
python3 scripts/asset-bundle.py verify /private/f8-bundle
```

`export` не скачивает данные и не перезаписывает существующий каталог: каждый входной файл уже должен совпадать с SHA. Для скачанного готового bundle нужен только `verify`. Каталожный пакет, media и рекомендации размещаются **отдельно**; команды распаковки комплекта и пересборки обоих индексов — в [инструкции переноса](ASSET-TRANSFER.ru.md). Код подготовки своих данных и проверка пакета — [контракт импортёра](../contracts/catalog-display.md) и [CLI в apps/api](../apps/api/README.md#be-045-реальный-каталог). Не подменяйте точный индекс рекомендаций визуальными соседями модели: это разные форматы и задачи.

### Состояние полного комплекта

По состоянию на 28 сентября 2026 [папка с полным комплектом](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ) доступна без авторизации: имена и SHA-256 всех 14 файлов совпали с локальными оригиналами (13 из них перечислены в `SHA256SUMS`; сам файл сумм не может содержать собственный хеш). Архивы по публичной ссылке не скачивались. Это проверка доступности и контрольных сумм, **не лицензия** на повторное распространение данных. Публичные веса исходных моделей из [описи](../deploy/assets/INVENTORY.md) не заменяют производный индекс, каталог и media; исходный код CPU-сервиса находится в `apps/vision/`. С локальным комплектом проверены полный запуск Compose и health/catalog smoke на Mac/OrbStack с linux/amd64-образами; запуск на отдельном чистом Linux и контрольное распознавание по известному фото ещё не подтверждены. Токен команды для локального API не нужен.

## Полный режим с Docker

Этот профиль запускает PostgreSQL 18, одноразовые миграцию/импорт, CPU-сервис компьютерного зрения и веб-приложение. Для планирования хоста нужны:

- Linux x86-64, Docker Engine с Compose v2, Python 3.11+, GNU `sha256sum`, `tar`, `curl` и `openssl`.
- Место под скачанные архивы (~4,3 ГиБ), распакованные `f8-bundle/` (~3,7 ГиБ), `catalog-media/` (~555 МиБ), Docker-образы (только vision ~1,48 ГБ), БД и загружаемые фото. Потоковая распаковка частей весов не создаёт дополнительную копию цельного архива. Не считайте сумму этих размеров проверенным минимумом свободного диска.
- RAM для vision-контейнера (установлен лимит 7 GiB) **плюс** PostgreSQL, API, Docker и ОС. Минимум RAM хоста на чистом Linux не измерен; ориентир для планирования — 16 ГиБ, не проверенная граница работоспособности. GPU не требуется.

Распакуйте архивы [по инструкции](ASSET-TRANSFER.ru.md#как-восстановить-на-linux) в `$HOME/brutforce-local`. Из корня клона один раз выполните `init`: он создаст отдельные локальные пароли и `deploy/.env.local` с путями к данным. Повторный `init` не перезаписывает существующую конфигурацию; для своего расположения данных передайте другой абсолютный путь. Для **другого** согласованного набора должны одновременно совпадать `CATALOG_VERSION`, manifest SHA в `scripts/docker-local.sh` и `RECOMMENDATION_INDEX_SHA256`.

```sh
sh scripts/docker-local.sh init "$HOME/brutforce-local"
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
curl --fail-with-body --max-time 10 -F 'image=@/path/to/approved-sample.jpg' \
  http://127.0.0.1:8097/v1/eval/predict
sh scripts/docker-local.sh stop
```

`up` **сам вызывает `preflight`** (32 SHA внешних данных, точные manifest/index SHA, secrets и Compose-конфигурация), строит образы с [кодом распознавания из репозитория](../apps/vision/README.md), применяет миграции/импорт и ждёт готовности. `smoke` проверяет health и каталог, **не** точность модели: известное разрешённое фото должно дать HTTP 200 и `{"slug":"точный-slug"}`. `stop` сохраняет volumes; `down` снимает контейнеры/сеть без удаления volumes. Скрипт рассчитан на один закреплённый комплект — произвольные файлы или другую версию каталога он не примет.

### Bootstrap на Mac

Нужны работающий Docker с Compose v2, Python 3.11+, `bash`, `curl`, `openssl` и `tar`. Для Apple Silicon Docker должен выделять достаточно памяти для vision (лимит контейнера 7 ГиБ), базы и веб-сервиса. Из чистого клона `main`:

```sh
git clone https://github.com/ai-babai/brutforce.git
cd brutforce
bash scripts/bootstrap-local.sh
```

Скрипт скачивает с [публичного Яндекс Диска](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ) только файлы для работы сервиса: данные распознавания, шесть частей весов, каталог, media и рекомендации. Он проверяет закреплённый SHA-256 манифеста, хеши архивов, собранного потока весов и содержимого `f8-bundle/`, затем создаёт локальные пароли, строит Compose и проверяет `/readyz`, каталог и health. Данные и архивы остаются вне Git в `$HOME/ml-data/brutforce/local-demo/`; промежуточные файлы для **пересборки** визуального индекса не скачиваются. На Mac vision работает в `linux/amd64`, остальные сервисы используют доступную архитектуру Docker. Compose-проект получает отдельное имя по пути к данным, чтобы не задеть имеющиеся локальные volumes.

Если комплект уже скачан, передайте каталог архивов вторым аргументом и собственный каталог для распаковки первым — скрипт проверит архивы без обращения к Яндекс Диску:

```sh
bash scripts/bootstrap-local.sh "$HOME/ml-data/brutforce/my-demo" /absolute/path/to/archives
```

Откройте <http://127.0.0.1:8097/>. На этом Apple Silicon Mac из чистого клона с готовыми локальными архивами и кэшированными Docker-слоями запуск до успешного smoke занял **3 минуты 10 секунд**. Первичная загрузка по сети и холодная сборка образов добавят время; архивы занимают около 4,3 ГиБ. Прямая проверка двух разрешённых фото через модель заняла примерно по 27 секунд:

```sh
bash scripts/bootstrap-local.sh photo /absolute/path/to/approved-photo.jpg
sh scripts/docker-local.sh stop
```

Команда `photo` возвращает `slug` непосредственно от локального CPU-сервиса внутри Compose. Она обходит Go API: конкурсный `/v1/eval/predict` на этом Mac прервал запрос через 9 секунд (HTTP 504), пока модель продолжала работу. Таким показом можно подтвердить локальный инференс, но не успешный ответ конкурсного API в установленный срок. На Linux x86-64 для сквозной проверки используйте запрос `curl` из предыдущего раздела.

## Полный режим без Docker

Это ручная сборка компонентов, **не подтверждённая end-to-end на чистом Linux**. Используйте её только с тем же проверенным комплектом; без него конкурсный API остаётся недоступен. Зависимости: PostgreSQL 18, Go 1.23, Node.js 22, Python 3.12, Tesseract с русским/английским OCR и пакеты из [vision-requirements.txt](../deploy/assets/vision-requirements.txt). За примером настройки PostgreSQL и разделения роли миграций/чтения смотрите [контракт БД](../contracts/database.md). Порядок запуска и переменные соответствуют [Compose](../deploy/compose.yaml), [vision bridge](../scripts/docker-vision-bridge.py) и [migrate](../scripts/docker-migrate.sh):

1. Проверить bundle командой `python3 scripts/asset-bundle.py verify /absolute/f8-bundle`; установить Python-зависимости в собственное окружение и предоставить внешние `models/hub`, `onnx/`, `ocr/` через `HF_HOME`, `NIGHT_SO_ONNX_DIR`, `TESSDATA_PREFIX`. Задать `F0_BASE_CODE_DIR` на абсолютный путь `apps/vision/parent` **клона**, `F8_OCR_LEXICON_SPEC` на `apps/vision/overlay/spec/lexicon.json`, а `PYTHONPATH` — на каталог parent.
2. Запустить `apps/vision/overlay/night_server.py` с `--catalog /absolute/f8-bundle/catalog/catalog-bundle.json --index-dir /absolute/f8-bundle/index --host 127.0.0.1 --port 8126 --threads 6 --encoder so400m --route onnx640`; дождаться `/healthz`.
3. Настроить свою БД: `MIGRATION_DATABASE_URL` для миграции/импорта, отдельный `DATABASE_URL` для HTTP; из `apps/api/` выполнить `go run ./cmd/catalog-migrate -schema-only`, затем экспортировать исходный снимок через `go run ./cmd/catalog-import -export-snapshot /private/before.json`. Проверить каталог командой `go run ./cmd/catalog-import -package /absolute/catalog-package -media-root /absolute/catalog-media -version VERSION -previous-snapshot /private/before.json -dry-run`; затем импортировать с `-snapshot-out /private/before.json` вместо `-dry-run`, а для проверки БД — с `-previous-snapshot /private/before.json -verify-db`. Снимок первого запуска может быть пустым, если БД действительно пустая.
4. Собрать UI: `npm --prefix apps/web ci && npm --prefix apps/web run build`. Для Go API задать `WEB_ROOT` на `apps/web/dist`, `UPLOAD_DIR` вне web root, `VISION_SERVICE_URL=http://127.0.0.1:8126`, `VISION_CATALOG_VERSION`, `VISION_INDEX_VERSION`, `VISION_SLUGS_FILE`, `VISION_SLUGS_SHA256`, `RECOMMENDATION_INDEX_FILE` и `RECOMMENDATION_INDEX_SHA256` из **того же** согласованного комплекта, затем запустить `go run .` из `apps/api/`. Доступ к `/media/catalog/…` требует отдельно настроенного файлового HTTP-сервера для разрешённых WebP; Compose включает его готовую реализацию в `web-proxy`.

Ручная установка не эквивалентна подтверждённому Compose-выпуску: пока не проверены совпадение OCR-версии, права на данные и полный прогон с известным фото. Если вам нужен повторяемый полный путь, используйте Compose с согласованным комплектом, а не смешивайте его версии.
