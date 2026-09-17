# 92_reports — отчёты о данных

Здесь хранятся безопасные агрегированные schema/quality/leakage summaries.
Крупные изображения, персональные данные и содержимое приватных сообщений в
отчёты не копируются. Каждый отчёт указывает версии входных манифестов и команду
воспроизведения.

Основные результаты:

- `DATASET-AUDIT-2026-09-15.md/.json` — итоговый cross-source gate;
- `BBOX-VISUAL-QA.md` — геометрическая и выборочная визуальная QA боксов;
- `CROSS-SOURCE-DUPLICATES-REVIEW.md` — exact/dHash проверка между источниками;
- `review_queue_*.jsonl` — явные очереди ручной проверки без автолейблинга.

Пересборка: `scripts/dataset/build_review_queues.py`,
`scripts/dataset/audit_cross_source_duplicates.py`,
`scripts/dataset/audit_all_datasets.py`.
