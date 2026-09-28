# BrutForce / Брютфорс

Репозиторий команды соревнования **ЛЦТ 2026**. Ищем существующую карточку российского вина по фото этикетки. Участники: Максим Попков (`ai-babai`) и Роман (`@MisterMolox`). [English](README.en.md).

[Прототип](https://app.dzap.pw) · [Запуск с моделью](#запуск-с-моделью) · [Локальное демо](#быстрый-запуск) · [Результаты и ограничения](docs/SOLUTION.md)

**Ссылки для сдачи**

- **Репозиторий:** [ai-babai/brutforce](https://github.com/ai-babai/brutforce) — приватный; доступ эксперта проверяется.
- **Документация:** [вход в документацию](docs/README.md) — в том же репозитории.
- **Презентация:** ссылка ожидается после утверждения файла и прав.
- **Прототип:** [app.dzap.pw](https://app.dzap.pw).

## Запуск с моделью

Нужны Linux x86-64, Docker Engine с Compose v2, Python 3.11+, `curl`, `openssl` и память для модели и каталога. Полный порядок получения, проверки, настройки паролей и сохранения данных — в [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8) ([English entry](docs/RUNBOOK.en.md)).

Получите через согласованный канал команды **четыре отдельные части**: проверенный F8 bundle, пакет каталога, media каталога и точный файл индекса рекомендаций. Если доступ к ним не выдан, обратитесь к Максиму Попкову (`ai-babai`) или Роману (`@MisterMolox`); ссылки для самостоятельного скачивания нет. Без точного файла рекомендаций `preflight` остановится — другой индекс его не заменяет.

Разместите полученное **вне клона**. На своей Linux-машине задайте абсолютный корень:

```sh
DATA_ROOT="$HOME/brutforce-local"
mkdir -p "$DATA_ROOT"
DATA_ROOT=$(realpath "$DATA_ROOT")
```

Структура внутри `$DATA_ROOT`:

```text
f8-bundle/
catalog-package/manifest.json
catalog-media/
recommendations/index.json
secrets/db_password
secrets/app_password
```

При первой настройке из корня клона скопируйте пример: `cp deploy/docker.env.example deploy/.env.local`. В `deploy/.env.local` впишите **развёрнутые абсолютные пути** с префиксом из результата `$DATA_ROOT`, а не буквальный `$DATA_ROOT`:

- `ASSET_DIR` → `f8-bundle/`; `CATALOG_PACKAGE_DIR` → `catalog-package/`.
- `CATALOG_MEDIA_DIR` → `catalog-media/`; `RECOMMENDATION_INDEX_FILE` → `recommendations/index.json` (**файл**).
- `SECRETS_DIR` → `secrets/` с двумя файлами паролей по [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8). Сохраните закреплённые `CATALOG_VERSION` и `RECOMMENDATION_INDEX_SHA256` из примера.

Когда комплект получен и настроен, из корня клона:

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

`preflight` сверяет bundle, каталог, индекс, секреты и Compose. `up` ждёт готовности сервисов; `smoke` проверяет HTTP health и каталог. Для контрольного запроса используйте разрешённое фото с известным ответом: ожидается HTTP 200 и тот же непустой `slug`. `stop` сохраняет данные. Текущую готовность полного Compose и требуемых внешних частей смотрите в [ограничениях](docs/SOLUTION.md#воспроизведение-и-ограничения).

## Быстрый запуск

Это локальное **синтетическое демо** без распознавания этикетки. Нужны Go 1.23, Node.js 22 и npm; PostgreSQL не требуется. Из корня клона откройте два терминала.

Первый:

```sh
mkdir -p ./local-uploads
cd apps/api
UPLOAD_DIR="$(pwd)/../../local-uploads" \
  go run .
```

Второй (снова из корня):

```sh
cd apps/web
npm ci
npm run dev
```

Откройте <http://127.0.0.1:5190/> и проверьте API: `curl --fail http://127.0.0.1:8097/v1/health`. Остановите оба процесса Ctrl-C. Загруженные фото в `local-uploads/` удаляет только владелец. Конкурсный endpoint в демо отвечает `503 recognition_unavailable`.

## Как это работает

1. Мобильный React-интерфейс принимает фото или текстовый запрос.
2. Go API хранит загруженное фото приватно и читает карточки из PostgreSQL.
3. Отдельный CPU-сервис выделяет этикетку, сравнивает визуальные признаки и при необходимости использует текст для ранжирования slug.
4. Go API проверяет slug и показывает существующую карточку, когда она есть в каталоге витрины. Конкурсный [`POST /v1/eval/predict`](contracts/eval-predict.md) принимает поле `image` и отвечает slug.
5. Отдельный закреплённый индекс предлагает похожие карточки по тексту и атрибутам винодельни; он не заменяет распознавание. [Подробная архитектура](ARCHITECTURE.md).

Измерения, версии и границы проверок — в [решении](docs/SOLUTION.md). [Карта репозитория](MAP.md) · [Контракты](contracts/README.md) · [Выпуск и откат](deploy/PIPELINE.md). Репозиторий остаётся приватным; лицензия на код пока не согласована, права на сторонние материалы проверяются отдельно.
