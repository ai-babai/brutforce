# Запуск и обслуживание · 28.09.2026

Основной runbook для локального демо и упакованного CPU-профиля F8. [English entry](RUNBOOK.en.md) ссылается на те же команды. Описание серверного выпуска и approval — [deploy/PIPELINE.md](../deploy/PIPELINE.md). Скрипты и 50-файловый SHA-манифест уже в репозитории; **передача внешних bytes и clean-Linux запуск пока не проверены**.

## Предварительные условия

- Локальное синтетическое демо: Go 1.23, Node.js 22, npm; любая поддерживаемая ими ОС. Без базы и весов. Храните реальные фото в непубличной папке.
- Реальный F8 CPU: Linux x86-64 с Docker Engine и Compose v2 **или** настроенные отдельно Go/API, PostgreSQL и vision runtime; достаточно свободной памяти для модели и индекса (точный лимит для чистого Linux запуска не подтверждён). CPU-сервис должен прогреться до readiness до первой оценки; предыдущая cold-load проба была 15,453 с.
- Обязательные внешние bytes и права на их получение: код F8 с parent imports, веса/детектор, SO400M/препроцессинг, OCR lexicon, индекс и metadata, allowlist slug, mapping витрины, media каталога, recommendation index и все зависимые версии. Нельзя скопировать только шесть SHA из [f8-runtime.json](../deploy/f8-runtime.json) и считать сборку полной.

## Локальное демо без ML

Из корня клона выполните ровно [команды README](../README.md#быстрый-запуск) в двух терминалах. Проба liveness: `curl --fail http://127.0.0.1:8097/v1/health`. Это не readiness БД или F8. `POST /v1/eval/predict` без F8 предсказуемо отвечает 503; никогда не использовать демо как оценку точности. Остановить оба процесса Ctrl-C. Папка `local-uploads/` игнорируется Git, но её содержимое удаляет только владелец данных.

Быстрые локальные проверки (после установки npm-зависимостей):

```sh
cd apps/api && go test -count=1 ./...
cd ../web && npm test && npm run build
```

От корня репозитория можно запускать `node scripts/run-fast-checks.mjs`; он создаёт историю отчётов, а не доказывает работу F8 или реальной камеры. Для SQL-интеграции нужен выделенный тестовый PostgreSQL и отдельные runtime/migration credentials; [правила БД](../contracts/database.md). Не направляйте миграции на чужую/production БД.

## Полный CPU-профиль F8

**Приёмка передачи assets pending.** Код упаковки уже в репозитории: [50 SHA](../deploy/assets/f8-cpu.sha256), [экспорт и проверка](../scripts/asset-bundle.py), [Compose](../deploy/compose.yaml), [env example](../deploy/docker.env.example), [операторский CLI](../scripts/docker-local.sh). Веса, исходный F8-код, каталог, изображения и индекс рекомендаций не входят в clone: получить их можно только через разрешённый владельцем канал. Не подменять их похожим набором и не копировать с Sigma без отдельного поручения.

Оператор создаёт вне Git приватную JSON-карту семи групп `overlay`, `parent`, `onnx`, `index`, `catalog`, `models`, `ocr`: значения — **каталоги-источники**, а не отдельные файлы. Скрипт `export` сравнивает каждый исходный файл с SHA-манифестом, собирает новый каталог и затем повторно проверяет его. Если bundle уже передан, нужен только `verify`:

```sh
python3 scripts/asset-bundle.py export --sources /private/operator-sources.json --out /private/new-f8-bundle
python3 scripts/asset-bundle.py verify /private/new-f8-bundle
```

`export` откажется перезаписать существующий `--out`. Каталог `models` в карте указывает на root HF hub, а bundle содержит `models/hub/…`; имена исходных каталогов зависят от владельца assets и не хранятся здесь. Bundle расположен вне репозитория, как и [каталожный пакет](../contracts/catalog-display.md), отдельные media и файл рекомендаций SHA `f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f`.

Из **корня клона** на Linux x86-64, после получения именно этих четырёх внешних частей:

1. Создайте приватный `SECRETS_DIR` вне репозитория (права 0700). В нём должны лежать два разных файла `db_password` и `app_password`, каждый с непустой lowercase hex строкой и правами 0600. Например, на машине запуска (только если этот каталог новый):

   ```sh
   umask 077
   mkdir -p "$HOME/.local/share/brutforce-secrets"
   chmod 0700 "$HOME/.local/share/brutforce-secrets"
   openssl rand -hex 32 > "$HOME/.local/share/brutforce-secrets/db_password"
   openssl rand -hex 32 > "$HOME/.local/share/brutforce-secrets/app_password"
   ```

   Подставьте развернутый абсолютный путь этого каталога **вне клона** в `SECRETS_DIR` (не литерал `$HOME`). Не печатайте значения и не помещайте их в аргументы команд, Docker layers или Actions artifacts. Не запускайте этот блок повторно на сохранённой БД: пароли перестанут совпадать с созданной ролью.
2. `cp deploy/docker.env.example deploy/.env.local`; замените абсолютными путями `ASSET_DIR`, `CATALOG_PACKAGE_DIR`, `CATALOG_MEDIA_DIR`, `RECOMMENDATION_INDEX_FILE`, `SECRETS_DIR`. `CATALOG_VERSION` и `RECOMMENDATION_INDEX_SHA256` оставьте закреплёнными, если владелец не выдал новый согласованный комплект. `deploy/.env.local` исключён из Git. Не вставляйте пароли в этот файл.
3. Выполните команды ниже. `preflight` сверяет 50 SHA, SHA каталожного manifest и рекомендаций, проверяет наличие секретных файлов и конфигурацию Compose. `up` строит образы, мигрирует **локальную** БД, сохраняет снимок каталога в named volume, импортирует и проверяет каталог, затем ждёт healthy vision/web. `smoke` проверяет HTTP health/catalog; он **не** является проверкой known-answer и OCR parity.

```sh
sh scripts/docker-local.sh preflight
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
```

Сервис доступен только на `http://127.0.0.1:8097` машины запуска. После `smoke` выполните показанный ниже конкурсный запрос с **разрешённым фото и известным slug**, затем проверьте `POST /v1/photos` → `POST /v1/search` → карточку. При завершении `sh scripts/docker-local.sh stop` останавливает сервисы, `sh scripts/docker-local.sh down` удаляет контейнеры/сеть **без `-v`**: DB, uploads, feedback и snapshots сохраняются. Повторный `up` использует существующие volumes, поэтому перед сменой версии каталога требуется отдельный план миграции и восстановления. Не используйте `docker compose down -v` для сохранённых данных.

Статус проверки: синтаксис скриптов и `docker compose config` проверены, но образы, внешний asset transfer, clean-Linux запуск, Tesseract/OCR parity и known-answer через Compose не подтверждены. Работающий [PROD](https://app.dzap.pw) запущен через systemd, а не эту упаковку.

Контрольный конкурсный запрос к **уже работающему реальному** API с разрешённым локальным фото (не использовать в демо без F8):

```sh
curl --fail-with-body --max-time 10 -F "image=@/path/to/approved-sample.jpg" http://127.0.0.1:8097/v1/eval/predict
```

Ожидается HTTP 200/201 и JSON с одним непустым `slug`, равным известному gold для фото; один корректный JSON не доказывает accuracy. В продукте `POST /v1/photos` принимает поле `photo`, затем `POST /v1/search` принимает JSON с `photoId` и выдаёт существующие карточки. [Контракт](../contracts/vision-serving.md). Не передавайте личные фото в публикации, PR и логах.

## Обновление, PROD и откат

Публичный TEST — <https://test.ops.dzap.pw>; PROD — [app.dzap.pw](https://app.dzap.pw) (`d26afa3`/`b0428147…`, F8 CPU, выпуск 28.09.2026). Обновление на Sigma делает назначенный оператор по [PIPELINE](../deploy/PIPELINE.md) для **точного** candidate: release archive, каталог, модель, mapping, recommendation override и policy. PROD credentials/uploads/feedback отделены от TEST. Не копировать окружение целиком, не запускать третью модель вслепую. При первом откате вернуть прежний маршрут-заглушку, остановив только новый app; не стирать данные и не останавливать чужой vision. SQL schema автоматически не откатывается. Читателю публичного клона не нужны и не предоставляются серверные `/srv`-пути или полномочия оператора.
