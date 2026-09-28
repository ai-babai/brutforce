# Выпуск BrutForce: TEST → PROD

Согласовано Максом 2026-09-21, INFRA-038. GitHub Free, приватный репозиторий.
Короткая ветка задачи → PR с CI → main → пакет → TEST → сводка → разрешение → PROD.
Ветки окружений не создаём. Preview Макса/Ромы независимы от общей выкатки.

## Составной кандидат

Кандидат фиксирует Git SHA/архив приложения, SHA-256 точных байтов manifest каталога,
режим и версию модели. Новый manifest при прежнем Git SHA — новый кандидат без пересборки.
Разрешение PROD относится к `candidateId`; старые demo-записи по Git SHA сохраняются.

Короткий путь для **следующих TEST-правок только данных/фото**: не пересобирать
тот же код и не повторять CI. Прогнать `catalog-import --dry-run` с актуальным
DB snapshot, зарегистрировать новый manifest командой `register-data`, затем
`deploy-test CANDIDATE_ID`. Контроллер сам сверяет media, экспортирует БД перед
изменениями, импортирует и проверяет публичные HTTP/photo пути. Для изменения
кода нужен один новый успешный main CI и его неизменный пакет; не копировать
локальный бинарник мимо контроллера. Chromium — только при конкретном дефекте.

Подготовленный каталог регистрируется после успешных DQ001..DQ008 и DQ011. Обязательные
`missing`, `skipped`, `error` и `failed` блокируют регистрацию. Контроллер повторно сверяет
manifest и все установленные bytes и запрещает повтор версии с другим manifest SHA:

```bash
sudo -n -u lct-release /usr/local/bin/lct-release register-data APP_FULL_SHA < data-quality.json
```

Полученный 64-символьный `candidateId` передаётся в `deploy.yml`. Перед первой мутацией БД
импортёр экспортирует snapshot; после импорта DQ009 проверяет БД, DQ010 — публичный Caddy
media URL, exact bytes/MIME/cache и закрытость internal. Browser evidence привязан к той же
комбинации. Сырой отчёт остаётся защищённым; status.json содержит сводку для Ops.

## Режим reference-модели

`reference`, модель `reference-demo-v1`, каталог `demo-v1`: восемь синтетических карточек.
Текст ищется по тестовому каталогу, рекомендации детерминированы. Фото валидируется,
но НЕ распознаётся: результат показывает только работу интерфейса и HTTP-контракта.
Конкурсный `/v1/eval/predict` к заглушке не подключён. ML-качество = `not_measured`.
Переход на реальную модель — новый кандидат, каталог/индекс/контрольный набор и метрики;
реальный каталог допускается отдельным составным кандидатом; режим модели остаётся честно
помеченным `reference`, пока отдельный выпуск не принесёт проверенную реальную модель.

Для кандидата TEST с F8 `deploy/f8-runtime.json` фиксирует `mode=real`, HTTP
`modelVersion` и SHA-256 шести внешних assets (overlay, родитель, OCR lexicon,
allowlist, соседи, индекс). Эти assets не входят в архив приложения: CI
записывает ожидаемые SHA и версию, но не доказывает, что внешние байты на Sigma
совпадают или что F8 активен. Перед switch необходимы отдельные read-only
сверка байтов с достаточными правами и `/healthz` реального vision-сервиса,
а также TEST-only план переключения и возврата к старому vision.
Контроллер под одной блокировкой повторно сверяет шесть SHA через ограниченный
root helper, запускает отдельный F8 на loopback :8126, требует `/healthz` и
известное приватное фото до миграции. При switch вместе с `current` меняется
TEST-only `vision-runtime.env`; публичный smoke сверяет фото и точный modelVersion.
Старый :8125 остаётся готовым к откату. Для установки отдельных TEST-only
unit/drop-in/helper и controller не запускать `bootstrap.py` целиком.
Проверенный data-switch рекомендаций закрепляется по точному SHA: при следующем
совместимом TEST deploy контроллер сверяет bytes, ID активного display-каталога
и версии, затем переносит receipt на новый appCandidateId. При несовместимости
switch останавливается до изменения `current` и env. Для следующих real TEST
и первого PROD обязателен exact cleaned SHA `f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f`;
отсутствующий receipt не даёт fallback на базовые visual-neighbors F8.

## Проверки и артефакт

`.github/workflows/ci.yml`: Go/Vitest, настоящая временная PostgreSQL18,
повторное применение миграций/seed и ограничения runtime-прав, контрактный прогон.
CAT-010…CAT-013 проверяют текстовый поиск; CAT-014 обязателен на настоящей тестовой БД.
Browser smoke проверяет переставленные слова с опечаткой через UI и рабочий API.
`deploy/check.sh` требует успешные Go/Eval/Vitest, реальное PostgreSQL evidence и
прохождение каждого BDD-кейса по умолчанию. Полный fast-report может оставаться
`partial` только для точных ID из версионируемого
`deploy/fast-report-exceptions.json` с причиной и альтернативным свидетельством.
Chromium-проверки AIR и DESIGN запускаются отдельно при конкретной проблеме; они
не входят в обязательный fast-report/CI. Непроверенный ими BDD ID остаётся
`skipped` до появления подходящего свидетельства.
Любой `failed`/`error`, новый пропуск или устаревшее исключение блокирует выпуск.
`checks.json` отдельно сообщает о результате обязательного набора (`status`) и
полноте всей карты BDD (`bddCoverageStatus`, `coverageExceptions`). Отчёт,
политика и её SHA-256 входят в пакет; это не превращает пропущенные кейсы в пройденные.
По разрешению Макса от 2026-09-28 медленные Chromium-BDD не входят в обязательный
fast gate. Точные ID остаются `skipped` и фиксируются в policy и immutable package;
пакет получает `targetScope: test-only`. AIR-025 закрывается только обязательным
реальным photo smoke на TEST после переключения F8. TEST-only исключения сами
по себе не дают права продвижения в PROD. Для первого CPU PROD действует
отдельная [fast-prod-v1](fast-prod-v1.json): только ровно 26 известных `skipped`,
поштучно отнесённых к superseded/deferred/required-live; `failed`, `error`,
новый skipped или иной SHA policy блокируют promote. Старый `checks.json` не
переименовываем в `all-environments` или полный BDD. Три required-live
(`DESIGN-009`, `AIR-025`, `AIR-043`) остаются отдельными поствыкаточными UI/HTTP
наблюдениями; автоматический PROD smoke покрывает фото и card API, но не UI целиком.
Действующий серверный контроллер обновляется отдельным infra-выпуском;
не направлять туда demo-only пакет до обновления. Для preview Макса используется
его отдельный контур, без переключения TEST/PROD.
`deploy/build.sh /absolute/output` создаёт пакет для Linux amd64 и SHA256 sidecar.
Требует чистую выделенную копию и отдельные тестовые DATABASE_URL/MIGRATION_DATABASE_URL.
На Sigma запускай DB-набор только внутри `lct-db-test maks`, не сбрасывай постоянные базы.

Архив: API, reference-engine, conformance, catalog-migrate, web, миграции,
REVISION, manifest.json и evidence. Секреты, пользовательские фото, веса и датасеты не входят.
Пакет из успешного CI main переносится без пересборки. SHA256 и содержимое manifest проверяются.
На GitHub доказательства хранятся 14 дней; установленный пакет и журнал остаются на Sigma.
Историю и пакеты пока автоматически не удаляем: политику очистки добавим по фактической потребности.

## Где работает

| Среда | Адрес | Current | База | Фото | API / заглушка |
|---|---|---|---|---|---|
| TEST | https://test.ops.dzap.pw | /srv/lct/stage/current | lct_shared | photos `/srv/lct/data/stage/photos`; feedback `/srv/lct/data/stage/feedback` | 8103 / 8113 |
| PROD | https://app.dzap.pw | /srv/lct/prod/current | lct_prod | photos `/srv/lct/data/prod/photos`; feedback `/srv/lct/data/prod/feedback` | 8104 / 8114 |

Все порты loopback. TEST публичный, без HTTP-пароля (решение Макса 2026-09-22).
Ops и OpenCode сохраняют авторизацию; не переносить её обратно на TEST.
API/заглушка — отдельные systemd units `brutforce-{test,prod}[-reference].service`.
PROD запущен; каждый новый candidate требует отдельного разрешения после TEST-проверки.
При самом первом выпуске app.dzap.pw переключался с существующей страницы-заглушки.
Это один сервер и один PostgreSQL-кластер, не независимые отказоустойчивые узлы.

## Управление через Actions и Sigma

Сначала `.github/workflows/deploy.yml`: `ci_run=<успешный main CI run ID>`, `target=test`.
Контроллер запускает F8, сверяет известное фото, затем переключает API и проверяет
реальный текст, рекомендации и фото; workflow проверяет внешний HTTP. Chromium
`deploy/browser-smoke.mjs` запускается отдельно как медленная диагностика, не в
обязательном CI/TEST workflow. Его реальный результат можно записать в серверный
журнал. Для первого CPU PROD `fast-prod-v1` допускает `browser: pending`, но
требует прошедшие CI/data/TEST/placement, exact TEST recommendation override
и явную human approval на bundle; browser `pending` остаётся видимым.

Sigma получает состояние без генерации проверки моделью:

```bash
sudo -n -u lct-release /usr/local/bin/lct-release status
```

Дополнительно проверь последние CI/Deploy через `sigma-gh run list` и нужный `run view`:
неудачная сборка ещё не имеет установленного пакета и потому не появится в серверном журнале.

Сводка человеку: SHA/изменения, какие проверки реально прошли, пропуски/риски,
режим модели и ссылки на CI, browser report, https://ops.dzap.pw/releases/.
«Все готово» не писать при pending/failed/неизвестном состоянии.

Только после явного поручения Макса или Романа продвинуть **названный** кандидат:

```bash
sudo -n -u lct-release /usr/local/bin/lct-release approve CANDIDATE_ID maks 'bb:thr_ygieygxmy6:<точная запись и время согласования>'
# Записывать только существующую ссылку на согласование exact candidate.
/opt/sigma-hermes/bin/sigma-gh workflow run deploy.yml --repo ai-babai/brutforce \
  -f ci_run=RUN_ID -f target=prod -f candidate_id=CANDIDATE_ID
```

Если Actions недоступен, после той же проверки и разрешения:

```bash
sudo -n -u lct-release /usr/local/bin/lct-release promote CANDIDATE_ID
```

Разрешение содержит SHA, actor, ссылку на поручение и технического записавшего.
Нельзя придумывать согласие, считать молчание согласием или брать новую версию вместо принятой.
Это организационная модель доверия: оператор с sudo/правом менять код может её обойти.
SSH-ключ Actions не может выдавать approve и не даёт обычную shell-сессию.
Нет платных Environments/обязательных reviewers. В Actions используем бесплатную квоту;
превышение бюджета не включаем. CI не запускает платные модели и полный датасет.

## Ошибка и откат

Одна серверная блокировка исключает параллельные переключения. Автоматического retry нет.
При неудачном smoke возвращаем предыдущий current (если был). При первой неудаче останавливаем новый сервис.
Миграция не откатывается автоматически; сбой миграции фиксируется, приложение ещё не переключено.
Перед PROD создаётся pg_dump. Откат приложения разрешён автоматикой только при одинаковых SQL-миграциях.
Иначе оператор сначала устанавливает совместимость; down/reset постоянных БД запрещён.
На failed initial PROD smoke контроллер возвращает Caddy placeholder из
`/etc/lct-release/pre-prod-caddy.backup`, удаляет новый `current`, останавливает
PROD units и снимает новый vision env. `pg_dump` и catalog snapshot сохраняются
для отдельной проверки/восстановления: миграция автоматически не отменяется.
TEST F8 при откате PROD не останавливать.

```bash
sudo -n -u lct-release /usr/local/bin/lct-release rollback PREVIOUS_FULL_SHA test
```

Sigma объясняет по-русски: что случилось, что успели, что осталось, что нужно от человека.
В назначенной карточке — Pending/подробности и ссылка на запуск; не закрывать её по exit процесса.
Выкатка сама не завершает продуктовую задачу и не создаёт новую разработку автоматически.

## Первый CPU PROD: fast-prod-v1

Это план установки только после согласования точного manifest владельцем deploy.
Сначала сверить SHA live controller с baseline, снять root-owned backup и
показать diff/SHA мастеру. Установить `release.py`, `fast-prod-v1.json`,
`publish-prod.py`, `unpublish-prod.py`, `lct-release-service.sh` и drop-in `lct-prod-f8.conf`
точечно; `bootstrap.py` целиком не запускать. Подготовить приватный `feedback`
под `/srv/lct/data/prod/` для `lct-release`, не переносить photos/feedback из
TEST. Drop-in подключает PROD-only catalog/vision env и FEEDBACK_DIR.
`prod-runtime.env`/`prod-migration.env` остаются в `/etc/lct-release` (0600),
значения секретов не выводить. До switch `prod/vision-runtime.env` ещё не
существует; при установке drop-in не перезапускать units.

Bundle: candidate ID, Git SHA, CI run, archive SHA, catalog manifest SHA,
шесть SHA F8 assets, recommendation SHA и model/index/catalog versions,
SHA `fast-prod-v1.json` и controller, actor, источник согласия и время.
`approve` закрепляет SHA только после проверки текущего TEST candidate/rec
receipt; `promote` повторяет сверку и требует готовый F8 :8126, не запуская
третью ML-копию. PROD имеет отдельные БД `lct_prod`, env, фото/feedback;
После первого PROD TEST deploy допускается только с теми же catalog manifest,
model version, external F8 assets, index и SQL-миграциями; запущенный F8 не
останавливается и не перезапускается. Повторный PROD с этими же инвариантами
снимает pg_dump, проверяет тот же cleaned recommendation receipt для точного
TEST candidate и approval нового bundle, меняет только код/окружение API.
Повторный switch не перепубликует Caddy и не пишет в БД каталога; при ошибке
возвращает прежний current, а опубликованный маршрут оставляет прежним. Для
ручного PROD rollback сначала верните прежний candidate на TEST: receipt снова
привяжется к нему, и exact approval можно будет проверить повторно. Контроллер
проверяет локальный и внешний HTTPS photo/catalog/recommendation smoke и
DQ009/DQ010 после publish. Реальное фото должно уложиться в 10 с с точным
slug/card; это один known-answer probe, а не оценка качества ML. Оставшиеся
required-live UI-наблюдения выполняются отдельно с фиксацией ограничений.

Перед первым таким повторным switch сравнить SHA установленного root-owned
`/usr/local/lib/lct-release/release.py` с исходником baseline, сохранить его
root-owned backup, проверить diff нового `deploy/release.py` из принятого `main`,
затем установить только controller с прежними владельцем и правами. Не менять
`lct-release-service.sh`, PROD Caddy или systemd unit ради code-only switch.

## Структура и обслуживание

`/srv/lct/releases/packages/<SHA>` — пакеты; `records/<candidateId>.json` — журнал
(старые `<SHA>.json` сохраняются);
`public/status.json` — сводка Ops. Это вывод выполнения, не ручные зелёные отметки.
`/usr/local/bin/lct-release` → root-owned `release.py`, исполнение от lct-release.
`/etc/lct-release` — конфиг и секретные env; в Git их значений нет.
`bootstrap.py` — операторская установка, не шаг каждого релиза; меняет только зарегистрированные службы.
Серверный runbook: `/srv/infra/lct-release/PIPELINE.md`. Меняешь pipeline — обнови этот файл,
карту проекта и infra-os. В AGENTS оставляй ссылку, а не копию всех правил.

## Runtime каталога BE-045

Данные находятся в `/srv/lct/data/catalog/releases/<version>/`, общие неизменяемые
изображения — в `/srv/lct/data/catalog/media/{400,800,original}/<sha>.webp`. Caddy отдаёт
только `/media/catalog/<role>/<sha>.webp`; release/internal не являются web-root.
Контроллер задаёт `CATALOG_VERSION` из кандидата и хранит фактическую комбинацию среды.

Для первого TEST alpha `svoe-20260927-alpha-2035-v1` данные содержат прозрачные
WebP 2035 из 2038 карточек. Три оставшихся непрозрачных фото временно не
передаются в API: клиент показывает штатное «Фото отсутствует». Базовый F8
индекс содержит визуальных соседей; проверенный TEST override
`display-text-attributes-winery-review-v2` содержит текстовых соседей для
2038 display ID текущего alpha-каталога и закреплён отдельным SHA. Это
атрибутивное сходство, не вкусовое/персональное и не метрика качества ML.
Для нового каталога нужен новый проверенный индекс/receipt; несовместимый
TEST override блокирует switch.

BE-089: read-only аудит прозрачности и локальная подготовка новых версионированных
media/manifest описаны в [catalog-alpha-be089.md](../docs/product/catalog-alpha-be089.md).
Новые alpha WebP не устанавливаются под уже зарегистрированной версией; полный
data gate, отдельный DB snapshot/import, HTTP и browser QA обязательны для каждой
целевой среды. Подготовленный частичный sample не является release candidate.
