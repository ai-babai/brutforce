# Отчёты быстрых проверок

`site/` — автономная статическая панель. `site/data/runs/` хранит неизменяемые JSON
снимки запусков; `site/data/index.json` перечисляет их в порядке времени. Запуск
добавляет новый файл, существующие снимки не переписывает.

Статус `not_run` означает, что проверки в момент baseline ещё не существовали.
Он не равен успеху или провалу. Результаты заглушки не являются измерением
распознавания вина.

## Новый запуск

Из корня: `RUN_LABEL="Название реализации" node scripts/run-fast-checks.mjs`.
Нужны Go и установленные зависимости apps/web. При необходимости GO_BIN указывает Go.
Открыть reports/site через HTTP. Дашборд постоянный: для новых данных достаточно обновить страницу.
Прогон сохраняет полное wall time в `timing.wallMs` (включая startup), время
процесса каждой suite, отдельно сообщённое раннером время и длительности
отдельных тестов. Сумма независимых top-level тестов приводится только как
справка: из неё не вычисляется startup/overhead, потому что вложенные и
параллельные тесты могут пересекаться. Go с `Elapsed: 0` показан как `<1 мс
(разрешение Go)`, а дробная длительность Vitest сохраняется без округления.
История ранних запусков без снимков оставлена как ограниченное свидетельство; это видно в деталях.

## Внешнее свидетельство Database

Обычный fast run не подключается к PostgreSQL. Поэтому DB-001…005 получают
`not_run`, если внешнее свидетельство не передано; это не успех. DB-006 — быстрый
Go mock отказа БД и входит в обычный Go API output.

На Sigma сначала соберите DB-набор и сохраните его JSONL вне репозитория. Текущий
предпочтительный запуск использует уже скомпилированный тестовый бинарник, чтобы
время DB-набора не включало компиляцию:

```sh
cd apps/api
go test -c -tags=integration -o db-tests .
go tool test2json -t -p brutforce-behavior-demo/apps/api ./db-tests -test.v -test.run '^TestDB00[1-5]' -test.count=1 > /absolute/path/db-test-results.jsonl
```

Рядом создайте `/absolute/path/db-test-metadata.json` с фактическими значениями:

```json
{
  "revision": "полный_git_HEAD",
  "wallMs": 1234,
  "command": "go tool test2json -t -p brutforce-behavior-demo/apps/api ./db-tests -test.v -test.run '^TestDB00[1-5]' -test.count=1"
}
```

Передайте оба абсолютных пути в fast runner и задайте точно ту же revision:

```sh
GIT_REVISION="полный_git_HEAD" \
DB_TEST_RESULTS_FILE=/absolute/path/db-test-results.jsonl \
DB_TEST_METADATA_FILE=/absolute/path/db-test-metadata.json \
node scripts/run-fast-checks.mjs
```

`DB_TEST_WALL_MS` можно передать только как запасной источник длительности, если
в metadata нет `wallMs`. Runner принимает свидетельство лишь при точном совпадении
`metadata.revision` и `GIT_REVISION`, наличии команды, итоговом package `pass` и
результатах всех DB-001…005. Плохой, устаревший или неполный явно переданный
результат сохраняется в immutable report, помечает run ошибкой и возвращает
ненулевой exit code. Время Database отображается отдельно и не входит в локальное
`timing.wallMs` («Весь запуск»).

## Отдельная проверка конкурсного API

Общий runner запускает тесты `TestEVAL` отдельным процессом Go и сохраняет
`*.eval-go.jsonl`, отдельную длительность и секцию «Конкурсный API — контракт».
Для короткого прогона: `cd apps/api && go test -count=1 -run '^TestEVAL' ./...`.
Успех этих проверок доказывает HTTP-контракт с подменённым распознавателем,
а не качество модели. Оригинальный скрипт организаторов запускается отдельно
на локальных закрытых примерах; исходные фото и выходы не коммитятся.

## Report behavior scenarios

- REPORT-001: Given a wide revision matrix, when scrolling horizontally, the scenario column and all section labels remain anchored with an opaque background. Fast test checks markup/CSS; actual scrolling is checked separately in a browser.
- REPORT-002: Given run records in arbitrary index order, when rendering the matrix, newest creation time comes first and baseline last.
- REPORT-003: Given past failures and a newer run, when rendering the summary, counts/status/time belong only to that latest run; skipped and not-run cases are not successful.
- REPORT-005: Given up to 2000 revisions and more than 40 scenarios, including a failure in a hidden row, when opening the report, the latest five revisions and first 40 scenario rows are shown. The full latest run determines the summary. More revisions are fetched in groups of five using dated index metadata; more rows appear in groups of 40. Failed fetches can be retried without moving the window or discarding a selected detail. Missing historical results remain `not_run`.

The index stores only revision metadata and paths. Full run JSON is loaded only for the visible revision window; historical path-only indexes remain readable. Each fast run refreshes the public case registry from `cases/cases.json`, so newly registered cases cannot disappear from the matrix.

Checks: `npm --prefix apps/web test -- --run src/report.test.ts`.
