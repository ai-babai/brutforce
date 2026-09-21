# Роман и его агент: начать здесь

Актуально: 2026-09-21. Это короткий маршрут; подробные правила — по ссылкам.

## Сначала

1. Прочитай [AGENTS.md](AGENTS.md), [MAP.md](MAP.md) и [правила команды](docs/agent-guide/RULES.md).
2. На сервере прочитай `/srv/AGENTS.md` и `/srv/lct/AGENTS.md`, затем правила рабочей копии.
3. Открой [SERVER.md](docs/agent-guide/SERVER.md), [DATABASE.md](docs/agent-guide/DATABASE.md) и CHECKLIST.md.
4. Сохрани локальную памятку по [LOCAL.md](docs/agent-guide/LOCAL.md) и ссылку на этот вход.

## Где работать

| Что | Где |
|---|---|
| SSH | `lct@217.26.30.220`, персональный ключ Романа, порт 22 |
| GitHub Романа | `MisterMolox`; сначала проверь авторизацию |
| Репозиторий | https://github.com/ai-babai/brutforce — приватный |
| Рабочая копия | `/srv/lct/work/<task>`; короткая ветка и PR в `main` |
| Данные Романа | `/srv/lct/data/roman`; исходники не менять без поручения |
| Общая БД | `lct_shared`; [правила](docs/agent-guide/DATABASE.md) |
| Тестовая среда | `/srv/lct/stage`, `test.ops.dzap.pw`, `lct_shared` |
| Production | `/srv/lct/prod`, `app.dzap.pw`, `lct_prod` — подготовлено, не подтверждает deployment |
| Заметки | `/srv/lct/notes/activity`; находки — `notes/inbox` |

`/srv/lct/repo` — общая интеграционная копия: проверь SHA/status, не делай reset и не меняй чужие файлы.
Секреты не копируй в Git, чат или отчёт. Папка, домен или БД не означают, что приложение запущено.
Runbook выпуска: [PIPELINE.md](deploy/PIPELINE.md). Базы и окружения сначала ищи в реестрах сервера.

## Поиск и рекомендации: BE-032

Перед реализацией прочитай [ROMAN-SERVICES.md](docs/agent-guide/ROMAN-SERVICES.md).
Он описывает HTTP-контракт, синтетический эталон, проверки и адреса подключения.
Референсная заглушка — явная заглушка: она не заменяет конкурсный endpoint и не подтверждает качество ML.

## Завершение задачи

- Перед стартом проверь [доску](https://github.com/users/ai-babai/projects/2) и [BOARD.md](docs/agent-guide/BOARD.md).
- Укажи инициатора, область, исполнителя и сессию; приложи проверку результата к карточке.
- Сначала открой короткую ветку, затем PR в `main`; не работай в чужой папке или ветке.
- Не публикуй и не деплой приложение без отдельного поручения.

## Если агент запущен на Windows

Используй OpenSSH из PowerShell и свой настроенный ключ. Bash-команды выполняй после входа по SSH.
Ключи и пароли здесь не хранятся.
