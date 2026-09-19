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

## Отдельная проверка конкурсного API

Общий runner запускает тесты `TestEVAL` отдельным процессом Go и сохраняет
`*.eval-go.jsonl`, отдельную длительность и секцию «Конкурсный API — контракт».
Для короткого прогона: `cd apps/api && go test -count=1 -run '^TestEVAL' ./...`.
Успех этих проверок доказывает HTTP-контракт с подменённым распознавателем,
а не качество модели. Оригинальный скрипт организаторов запускается отдельно
на локальных закрытых примерах; исходные фото и выходы не коммитятся.

## Report behavior scenarios

- REPORT-001: Given a wide revision matrix, when scrolling horizontally, the scenario column remains anchored with an opaque background. Fast test checks markup/CSS; actual scrolling is checked separately in a browser.
- REPORT-002: Given run records in arbitrary index order, when rendering the matrix, newest creation time comes first and baseline last.
- REPORT-003: Given past failures and a newer run, when rendering the summary, counts/status/time belong only to that latest run; skipped and not-run cases are not successful.

Checks: `npm --prefix apps/web test -- --run src/report.test.ts`.
