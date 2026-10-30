# Карта BrutForce

Текущий прод: **Boost V16 C16**, сверка 31.10.2026.

| Задача | Точка входа |
|---|---|
| Что работает в бою и как воспроизвести | [PRODUCTION.ru.md](docs/PRODUCTION.ru.md) |
| Версии, SHA исходников, весов и индексов | [production.json](deploy/production.json) |
| Продукт, API и быстрый вход | [README](README.md) |
| Распознавание C16 | [apps/vision/c16](apps/vision/c16/README.md) |
| Исходный retrieval и модельные primitives | [boost](apps/vision/boost/), [parent](apps/vision/parent/) |
| HTTP API, uploads и сопоставление карточек | [apps/api](apps/api/README.md) |
| Мобильный интерфейс | [apps/web](apps/web/AGENTS.md) |
| Границы каталогов, распознавания и загрузок | [contracts](contracts/README.md) |
| Проверки кода | `go test -count=1 ./...` в apps/api; `npm test` и `npm run build` в apps/web |
| Исторический F8, старый pipeline и исследования | [документация](docs/README.md) |

Старые F8/A2 receipts и `/release.json` не отражают эффективные systemd overrides.
Переход к новому Git commit не меняет работающий сервер.
