# Карта проекта BrutForce

Короткий вход для людей и агентов. Карта отражает текущий checkout; не загружай все документы подряд.
Назначение существующих зон и границы будущих: [INDEX.md](docs/project/INDEX.md).

| Задача | Куда идти |
|---|---|
| Что строим, как запустить | [README.md](README.md) |
| Поведение продукта | [Спецификации](docs/product/behavior-spec.md) |
| Изменение UI | [apps/web](apps/web/AGENTS.md), [Design Specs](apps/web/design-specs.md) |
| HTTP backend | [apps/api](apps/api/AGENTS.md), [API README](apps/api/README.md) |
| Связь модулей, конкурсный API | [contracts](contracts/README.md), [eval](contracts/eval-predict.md) |
| Поиск/рекомендации Романа | [Контракт](contracts/wine-services.md), [онбординг](docs/agent-guide/ROMAN-SERVICES.md) |
| Дизайн и макеты | [Переход на v2](docs/product/design-v2-migration-plan.md), design/ |
| Тестовые фото, поиск и сервисные проверки | [Eval onboarding](apps/eval/AGENTS.md), [стенд](https://cv.ops.dzap.pw/), [инструкция](https://cv.ops.dzap.pw/guide.html) |
| Проверки и история | [cases](cases/cases.json), scripts/run-fast-checks.mjs, reports/ |
| Совместная работа | [RULES](docs/agent-guide/RULES.md), [BOARD](docs/agent-guide/BOARD.md) |
| Выпуск и откат | [deploy](deploy/README.md), deploy/releases/ |
| БД и тестовые среды | [DATABASE](docs/agent-guide/DATABASE.md), [контракт каталога](contracts/database.md) |
| Полномочия и ограничения | [AGENTS](AGENTS.md), [подробности](docs/agent-guide/OPERATING-RULES.md) |
| Обновление структуры | [GUIDE-FORMAT](docs/agent-guide/GUIDE-FORMAT.md) |

Заметки описывают реальность или явно обозначенное предложение. Существование папки не означает готовность модуля.

## Vision pilot and standalone recognition

- Per-wine images, lineage and generation: [tools/vision-pilot/README.md](tools/vision-pilot/README.md).
- Frozen-suite OCR baselines and measured findings: [tools/vision-baselines/README.md](tools/vision-baselines/README.md).
