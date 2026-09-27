# Карта проекта BrutForce

Короткий вход для людей и агентов. Карта отражает текущий checkout; не загружай все документы подряд.
Назначение зон и их состояние: [INDEX.md](docs/project/INDEX.md).
Вход Романа и его агента: [ROMAN-START.md](ROMAN-START.md).

| Задача | Куда идти |
|---|---|
| Цель и запуск | [README.md](README.md) |
| Изменение UI | [apps/web](apps/web/AGENTS.md), [Design Specs](apps/web/design-specs.md) |
| HTTP backend | [apps/api](apps/api/AGENTS.md), [API README](apps/api/README.md) |
| Разметка тестовых фото | [Контракт feedback](contracts/photo-feedback.md), `apps/api/feedback.go`, UI-007 |
| Контракты и конкурсный API | [contracts](contracts/README.md), [eval](contracts/eval-predict.md) |
| Поиск и рекомендации Романа | [Контракт](contracts/wine-services.md), [онбординг](docs/agent-guide/ROMAN-SERVICES.md) |
| Дизайн и макеты | [Переход на v2](docs/product/design-v2-migration-plan.md), [Atlas](design/wine-ux-atlas/README.md) |
| Настоящий каталог | [BDD](docs/product/catalog-display-spec.md), [контракт](contracts/catalog-display.md) |
| Прозрачность бутылок BE-089 | [Аудит и demo-выпуск](docs/product/catalog-alpha-be089.md) |
| Качество данных | [Кейсы](cases/data-quality.json), [выкатка и отчёты](deploy/PIPELINE.md) |
| Проверки и история | [cases](cases/cases.json), `scripts/run-fast-checks.mjs`, reports/ |
| Совместная работа | [RULES](docs/agent-guide/RULES.md), [BOARD](docs/agent-guide/BOARD.md) |
| Выпуск, откат и среды | [PIPELINE](deploy/PIPELINE.md), [DATABASE](docs/agent-guide/DATABASE.md) |
| Полномочия | [AGENTS](AGENTS.md), [подробные правила](docs/agent-guide/OPERATING-RULES.md) |
| Обновление структуры | [GUIDE-FORMAT](docs/agent-guide/GUIDE-FORMAT.md) |

Приложение и runbook отражают состояние этой ветки. Папка или подготовленная среда не означает работающий выпуск.
