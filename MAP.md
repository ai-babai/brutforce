# Карта проекта BrutForce

Открой документ своей задачи. Состояние зон — в [INDEX.md](docs/project/INDEX.md); вход для Романа — [ROMAN-START.md](ROMAN-START.md).

| Задача | Куда идти |
|---|---|
| Цель и запуск | [README.md](README.md) |
| English entry | [README.en.md](README.en.md), [runbook EN](docs/RUNBOOK.en.md) |
| Эксперт: четыре ссылки сдачи, результаты и статус | [README](README.md), [результаты](docs/SOLUTION.md), [архитектура](ARCHITECTURE.md) |
| Внешний разработчик: без данных / полный режим | [Самостоятельный запуск](docs/SELF-HOST.ru.md), [архитектура](ARCHITECTURE.md) |
| Команда: закреплённый комплект и серверы | [Операционный runbook](docs/RUNBOOK.ru.md), [PIPELINE](deploy/PIPELINE.md) |
| Локальный Docker CPU F8 | [Код vision](apps/vision/README.md), [runbook](docs/RUNBOOK.ru.md#полный-cpu-профиль-f8), [Compose](deploy/compose.yaml), [32 SHA данных](deploy/assets/f8-cpu.sha256), [операторский CLI](scripts/docker-local.sh) |
| Скоринг фото на Apple Silicon без Docker и БД | [Mac bootstrap](scripts/bootstrap-mac.sh), [инструкция](docs/SELF-HOST.ru.md#скоринг-на-mac) |
| Полный Docker-стек с загрузкой данных | [Docker bootstrap](scripts/bootstrap-docker.sh), [инструкция](docs/SELF-HOST.ru.md#bootstrap-с-docker) |
| Изменение UI | [apps/web](apps/web/AGENTS.md), [Design Specs](apps/web/design-specs.md) |
| HTTP backend | [apps/api](apps/api/AGENTS.md), [API README](apps/api/README.md) |
| Разметка тестовых фото | [Контракт feedback](contracts/photo-feedback.md), `apps/api/feedback.go`, UI-007 |
| Контракты и конкурсный API | [contracts](contracts/README.md), [eval](contracts/eval-predict.md) |
| Поиск и рекомендации Романа | [Контракт](contracts/wine-services.md), [онбординг](docs/agent-guide/ROMAN-SERVICES.md) |
| Дизайн и макеты | [Переход на v2](docs/product/design-v2-migration-plan.md), [Atlas](design/wine-ux-atlas/README.md) |
| Настоящий каталог | [BDD](docs/product/catalog-display-spec.md), [контракт](contracts/catalog-display.md) |
| Прозрачность бутылок BE-089 | [Аудит и подготовка](docs/product/catalog-alpha-be089.md) |
| Качество данных | [Кейсы](cases/data-quality.json), [выкатка и отчёты](deploy/PIPELINE.md) |
| Проверки и история | [cases](cases/cases.json), `scripts/run-fast-checks.mjs`, reports/ |
| Права и публичность | [Граница прав](docs/SOLUTION.md#презентация-и-права), приватный аудит раскрытия у владельца |
| Совместная работа | [RULES](docs/agent-guide/RULES.md); доска задач больше не используется (см. [AGENTS](AGENTS.md)) |
| Выпуск, общий TEST/PROD F8 и повторный code-only switch | [PIPELINE](deploy/PIPELINE.md), [fast-prod-v1](deploy/fast-prod-v1.json), `deploy/release.py`, [DATABASE](docs/agent-guide/DATABASE.md) |
| P0 + automatic A2, поэтапный switch и откат | [Pipeline](deploy/PIPELINE.md#p0--automatic-a2), [CPU wrapper](apps/vision/README.md#automatic-a2-release) |
| Полномочия | [AGENTS](AGENTS.md), [подробные правила](docs/agent-guide/OPERATING-RULES.md) |
| Обновление структуры | [GUIDE-FORMAT](docs/agent-guide/GUIDE-FORMAT.md) |

TEST и [PROD](https://app.dzap.pw) используют общий CPU F8: app `d26afa3`, candidate `b0428147…` (28 сентября 2026). HTTPS и HTTP smoke с реальным фото пройдены. Документация вошла в приватный `main` на `b451ecd`; её последующие коммиты не меняют развёрнутый app. [Граница подтверждения](docs/SOLUTION.md#метрики-по-разным-наборам).
