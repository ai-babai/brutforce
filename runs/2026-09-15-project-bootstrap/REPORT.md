# VINO-000 — Bootstrap проекта

Дата: 2026-09-15
Статус: завершён локальный setup; независимый review не выполнялся.

## Результат

- Прочитано и визуально проверено всё исходное ТЗ из 6 страниц.
- Требования нормализованы в `PROJECT.md`, рекомендованный стек отделён от
  обязательных требований.
- Созданы корневые источники истины: навигация, архитектура, план, очередь и
  реестр ошибок.
- Создан Agents OS с компактной рабочей, фактической, эпизодической и
  процедурной памятью, протоколами handoff/data/memory lifecycle.
- Созданы 6 project-scoped custom agents без model/sandbox/provider overrides.
- Подготовлены локальные зоны данных, безопасные манифесты, splits, evaluation
  protocol и acceptance matrix.

## Источники

- `10. РСХБ.Цифра.pdf`: 478075 байт; SHA-256
  `78cc5cece58f5ffe4f48f513b424cdee26e0729820a167b61cde12531618ada9`.
- Соседние проекты: Beeline, Eonlings, Helper и Books — только как примеры
  структуры; проектные требования из них в Vino не переносились.
- Актуальное руководство Codex: repository `AGENTS.md`, `.codex/config.toml` и
  project-scoped custom agent TOML.

## Проверки

- `scripts/verify-project-setup.ps1` — PASS: обязательные файлы/каталоги,
  относительные Markdown-ссылки, обязательные поля 6 agent profiles и лимит
  `WORKING.md`.
- Python 3.12 `tomllib` — 7/7 TOML-файлов разобраны, exit code 0.
- `codex features list` — exit code 0; multi-agent feature stable/enabled.
- `codex doctor --summary --ascii --no-color` — project config loaded. Doctor
  также показал несвязанные с Vino глобальные замечания о terminal/старых
  rollout/thread records; они не являются результатом проекта.
- SHA-256 исходного PDF повторно совпал.

## Не проверено

- Профили появятся в новом сеансе Codex после повторного открытия доверенного
  проекта; текущая сессия была запущена до создания `.codex/agents/`.
- Независимый QA bootstrap не выполнялся.
- Код, данные, модель, GPU, UI, API, benchmark и SLA отсутствуют и не проверялись.

## Следующий шаг

`VINO-001`: принять фактический каталог и public field-image dataset по
`docs/data/COLLECTION-RUNBOOK.md` и создать первый versioned data manifest.
