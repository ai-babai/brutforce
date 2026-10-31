---
type: Deployment Guide
description: Облегчённый демонстрационный стенд BrutForce на Beget без PostgreSQL, распознавания и загрузок; читать для сборки, обновления и отката.
---
# BrutForce: демонстрационный стенд

Ветка `codex/brut-demo-stand` основана на производственном C16 commit `735127e`.
С 01.11.2026 приложение размещено на https://brut.mipopkov.ru/;
приватный архив — https://brut.mipopkov.ru/reports/.
Исторический C16 сохраняется в `main` и tag `production-c16-20261031`.
`deploy/production.json` описывает прежний модельный прод, а не этот стенд.

Работают каталог из **2038 реальных карточек**, три алиаса, ограниченная
пагинация, текстовый поиск, карточки, избранное в браузере и рекомендации
из сохранённой таблицы соседей. Сокращение каталога не выполнялось.
В ответах `demo:false` означает реальные каталожные данные, а не наличие модели.

**Распознавание отсутствует:** `/v1/photos`, `/v1/feedback`, `/v1/eval/predict`
и поиск с `photoId` возвращают `410 demo_read_only`. При установленном
`DEMO_STAND_CATALOG_FILE` API не создаёт photo/feedback store и не подключает
модельные HTTP-сервисы. Одновременная настройка `DATABASE_URL` запрещена.
Frontend собирается с `BRUT_DEMO_STAND=1`: камеры и file inputs нет,
главное действие — поиск, второе — архив отчётов.

## Файлы и процесс

```text
/srv/brut/
  current -> releases/20261101-demo
  releases/20261101-demo/
    api/brut-api
    web/
    catalog/{catalog.json,recommendations.json}
    reports/{index.html,maks/,roman/,project/}
  assets/
    catalog/
    synthetic/{media/,thumbs/}
/etc/brut/{runtime.env,site.caddy,reports-auth.caddy}
/etc/systemd/system/brut-api.service
```

Каталог и приватные отчёты не включены в Git. Они скопированы из действующего
прода/текущих отчётов, а не из исторических восьми синтетических fixtures.
`catalog.json` содержит `{version,wines,aliases}` с полной JSON-проекцией карточек.
SHA-256 каталога: `e27b6cee3c73188c4946b7b0887eb7942378cf7b7bc2cd133ce050a245a96c29`.
SHA таблицы рекомендаций закреплён в [runtime.env.example](../deploy/demo/runtime.env.example).
Изображения вынесены из релиза; галерея ссылается на общий `assets/synthetic`.

Один Go-процесс `brut-api.service` от пользователя `brut` без shell/sudo,
только `127.0.0.1:8098`. Caddy завершает TLS и отдаёт отчёты/изображения.
Владелец всех файлов — root, runtime их не изменяет. `ProtectSystem=strict`,
лимит памяти 256 МБ, CPU 100%, `/tmp` — tmpfs 16 МБ; сеть процесса ограничена
loopback. Нет каталогов для загрузок и записей feedback. Пакеты PostgreSQL,
Python/ML и Docker для демо не устанавливаются.

`/reports/` использует существующую Basic Auth Lab (логин `demo`, тот же пароль),
`private, no-store` и `noindex`. Секрет находится только в серверном
`reports-auth.caddy`, root:caddy 0640. В API допускаются POST только для
читающего поиска и рекомендаций; архив разрешает GET/HEAD/OPTIONS.
Caddy admin API на Beget сохранён по решению владельца.

## Сборка и обновление

```sh
cd apps/web
npm ci
BRUT_DEMO_STAND=1 npm run build
cd ../api
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o /external/staging/brut-api .
```

Подготовить новый каталог `releases/<release>`, положить бинарник, `dist/`,
проверенный внешний каталог и индекс. Общие изображения повторно не копировать.
Отчёты обновлять отдельной файловой выгрузкой; не включать веса или новые inputs.
Для исходного архива применён [archive-reports.py](../deploy/demo/archive-reports.py):
новые префиксы, архивные пометки, отключённые file inputs и живой сборщик.
Шаблоны [systemd](../deploy/demo/brut-api.service) и [Caddy](../deploy/demo/site.caddy)
должны соответствовать серверным. Caddy использует существующий snippet
`private-access-log`; auth-файл создаётся отдельно, в Git его нет.

После проверки сменить `current`, перезапустить только `brut-api`,
валидировать Caddy и выполнить reload при изменении маршрутов.
Проверить health, каталог/пагинацию, карточку, поиск, рекомендации, 410 на запись,
401 на отчёты без авторизации, изображения и пользовательский сценарий в браузере.
Для отката стенда вернуть `current` на предыдущий совместимый файловый релиз.
Возврат модельного прода требует восстановления весов с Mac и отдельного запуска;
простое включение старой службы на Sigma после миграции недостаточно.

## Архив отчётов

Главная `/reports/` содержит полный каталог **68 опубликованных страниц** с поиском
и разделами. Метаданные строятся из серверного архива, в Git не включаются:

```sh
python3 deploy/demo/build-report-catalog.py /srv/brut/current/reports
```

После переноса/обновления архива выполнить `archive-reports.py`, скопировать
`deploy/demo/reports-index.html` в `reports/index.html`, затем пересобрать каталог.
Корень `reps.maks.dzap.pw/` перенаправляет в полный каталог, `/view` сохраняет UX Atlas.

Сохранены текущие отчёты Макса и Романа, синтетическая галерея, behavior,
mascot-lab, wine-after-scan, UX v2/v3 с предыдущими вариантами, training dashboard,
презентация и видео. Eval сохранён как статическая страница с 98 прежними
прогонами и JSON-снимками `/api/baskets` и `/api/runs`; новые прогоны запрещены.
Исходные eval-изображения были удалены раньше и в архив не вошли:
вместо недоступного снимка показывается явное архивное пояснение;
скачивание входного eval-пакета отключено. Ручная проверка референсов завершена,
живой reviewer/collector не переносился. Исторические статусы/метрики не исправлялись.

Старые app/reports/landing/eval/training адреса на Sigma перенаправляют на Beget.
Пять старых BrutForce-служб остановлены и отключены. Десять файлов весов и
индексов (~3.94 ГБ) удалены с Sigma после повторной SHA-проверки локальных
97 исходников и 43 внешних assets. Общий системный Tesseract не удалялся.
Модельный комплект остаётся на Mac: `/Users/skif/ml-data/brutforce/production-c16-20261031/`.
Исторические отчёты и исходная БД на Sigma пока сохранены для восстановления.
