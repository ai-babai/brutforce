# Реестр зон проекта

Карта кода и согласованной структуры, 2026-09-22. Фактический выпуск сверяй с журналом Quality Gates.

| Зона | Назначение и состояние | Вход |
|---|---|---|
| `apps/web/` | React/TypeScript мобильное демо | `apps/web/AGENTS.md` |
| `apps/api/` | Go HTTP API, PostgreSQL-каталог, импорт/проверка данных, upload и eval boundary; ML пока reference | `apps/api/README.md` |
| `contracts/` | Канонические машинные интерфейсы и схемы | `contracts/README.md` |
| `cases/`, `scripts/`, `reports/` | Сценарии, быстрые проверки и история прогонов | `cases/cases.json` |
| `cases/data-quality.json` | Отдельные проверки каталога: файлы, мета, БД, HTTP и исчезнувшие ID | `contracts/catalog-display.md` |
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
- `/srv/lct/stage`, `test.ops.dzap.pw`, `lct_shared` — общая тестовая среда; текущий кандидат виден в Quality Gates.
- `/srv/lct/prod`, `app.dzap.pw`, `lct_prod` — подготовленная production-цель, не подтверждение deployment.
- `/srv/lct/data/catalog/releases/<version>` — неизменяемые метаданные каталога, манифест и происхождение; вне Git.
- `/srv/lct/data/catalog/media/{400,800,original}` — общие публичные WebP; имя — SHA-256 окончательных байтов.
- `/srv/lct/backups/catalog/<environment>` — снимки перед импортом; не публичная папка.

Проверки выкатки: [Quality Gates](https://ops.dzap.pw/releases/). Полный набор изображений
проверяется при изменении данных/схемы/правил; обычные тесты приложения используют маленькие fixtures.
Неожиданное исчезновение реальных ID блокирует обновление до разбора и согласования конкретных ID.
Исходники Романа и display-пакеты сохраняют происхождение; runtime не является ML-эталоном.

Серверные сведения: [SERVER.md](../agent-guide/SERVER.md); БД: [DATABASE.md](../agent-guide/DATABASE.md).
Не создавай пустые `apps/ml`, `inventory`, `db` и другие зоны заранее.
