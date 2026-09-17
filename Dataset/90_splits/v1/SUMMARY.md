# Split v1

Статус: `assignment_pending_identity_audit`.

[`SPLIT-CONTRACT.yaml`](SPLIT-CONTRACT.yaml) фиксирует роли, seed, доли
development pool и единицу разбиения. JSONL assignment-файлы намеренно не
созданы: данных с подтверждёнными item-level IDs пока нет.

После прохождения freeze gate появятся шесть manifest-файлов и leakage report.
Изменение assignment после заморозки создаёт `v2`, а не перезаписывает `v1`.
