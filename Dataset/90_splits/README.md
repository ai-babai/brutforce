# 90_splits — frozen роли

Версия хранится отдельным каталогом (`v1`, `v2`, ...). Внутри ожидаются
`catalog_reference.jsonl`, `train.jsonl`, `val.jsonl`, `test.jsonl`,
`holdout.jsonl`, `caseholder_eval.jsonl` и `SUMMARY.md`.

Запись содержит как минимум `media_id`, `role`, `identity_group_id`,
`near_duplicate_group_id`, `source_id`, версию и причину назначения. Роль не
выводится из физического пути. После заморозки любое изменение создаёт новую
версию; старые эксперименты не перепривязываются.

До окончания аудита идентичности в `v1/` есть только
[`SPLIT-CONTRACT.yaml`](v1/SPLIT-CONTRACT.yaml) и
[`SUMMARY.md`](v1/SUMMARY.md): assignment-файлы намеренно отсутствуют. Это
означает «контракт подготовлен», а не «split выполнен».
