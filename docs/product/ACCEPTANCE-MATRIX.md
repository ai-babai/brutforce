# Матрица приёмки Vino

Статус: draft; данные приняты, но item-level ground truth и контрольный скрипт
ещё не готовы. Источник требований —
`../../10. РСХБ.Цифра.pdf`, нормализация — `../../PROJECT.md`.

| ID | Требование | Наблюдаемое evidence | Уровень | Статус |
|---|---|---|---|---|
| ACC-001 | Фото из камеры/галереи | мобильный браузер загружает валидное фото и показывает состояния | e2e | open |
| ACC-002 | CV-поиск обязателен | inference trace содержит visual feature path; OCR-only режим не проходит | contract/integration | open |
| ACC-003 | Один лучший результат | оценочный endpoint возвращает ровно `{"slug":"..."}` | contract/e2e | open |
| ACC-004 | Достоверность | frozen public/holdout отчёт с exact top-1, top-5 recall, macro F1 | evaluation | open |
| ACC-005 | Near-duplicates | отдельные метрики и confusion groups по похожим этикеткам | evaluation | open |
| ACC-006 | Unknown wine | откалиброванный отказ без ложной карточки | evaluation/e2e | open |
| ACC-007 | Карточка вина | поля берутся из каталога по найденному `slug` | contract/e2e | open |
| ACC-008 | Mobile-first UI | фиксированные viewport-проверки и визуальный review | e2e/visual | open |
| ACC-009 | Дополнительная функция | отдельный пользовательский сценарий и критерий ценности | product/e2e | open |
| ACC-010 | SLA до 3 секунд | p50/p95/p99 warm и cold на описанном оборудовании | performance | open |
| ACC-011 | Локальный запуск | чистый setup/start и smoke по README/Docker | release | open |
| ACC-012 | Bash-совместимость | фактический скрипт кейсодержателя проходит на public наборе | acceptance | open |
| ACC-013 | Документация | актуальные README и ARCHITECTURE соответствуют release | review | open |
| ACC-014 | Происхождение данных | immutable raw, SHA-256 manifest, права и frozen split contract | data gate | prepared |

`open` не означает провал: реализация ещё не начиналась. Статус меняется только
после ссылки на сохранённый результат проверки в `docs/testing/` или `runs/`.
