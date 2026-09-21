# Реестр зон проекта

Проверено по release-pipeline checkout 2026-09-21. Это карта существующих зон, не требование их переносить.

| Зона | Назначение и состояние | Вход |
|---|---|---|
| `apps/web/` | React/TypeScript мобильное демо | `apps/web/AGENTS.md` |
| `apps/api/` | Go HTTP API, synthetic catalog, upload и eval boundary; реальный ML не подключён | `apps/api/README.md` |
| `contracts/` | Канонические машинные интерфейсы и схемы | `contracts/README.md` |
| `cases/`, `scripts/`, `reports/` | Сценарии, быстрые проверки и история прогонов | `cases/cases.json` |
| `design/` | UX-макеты и референсы, отдельно от API | `design/wine-ux-atlas/README.md` |
| `docs/agent-guide/` | Вход участников, сервер, БД и правила | `AGENTS.md` |
| `deploy/` | Runbook выпуска, отката и среды | `deploy/PIPELINE.md` |

## Веточная реальность

Приложение развивается короткими ветками `codex/<название>` и попадает в `main` через PR.
Перед работой сверяй ветку, SHA и наличие файла. Папка или подготовленная среда не означает работающий выпуск.

## Серверные зоны

- `/srv/lct/repo` — общая интеграционная копия; перед работой сверяй SHA, remote и status.
- `/srv/lct/work/<task>` — отдельные рабочие копии задач.
- `/srv/lct/maks`, `/srv/lct/roman` — зоны экспериментов; постоянные данные в `/srv/lct/data` вне Git.
- `/srv/lct/stage`, `test.ops.dzap.pw`, `lct_shared` — подготовленная общая тестовая среда.
- `/srv/lct/prod`, `app.dzap.pw`, `lct_prod` — подготовленная production-цель, не подтверждение deployment.

Серверные сведения: [SERVER.md](../agent-guide/SERVER.md); БД: [DATABASE.md](../agent-guide/DATABASE.md).
Не создавай пустые `apps/ml`, `inventory`, `db` и другие зоны заранее.
