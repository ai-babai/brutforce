# Интеграция Vino в BrutForce

Дата: 2026-09-17
Задача: `VINO-009`
Ветка: `codex/vino-integration`

## Результат прохода

- Приватный `ai-babai/brutforce` клонирован после штатной авторизации Git
  Credential Manager аккаунтом `MisterMolox`.
- Под отдельным worktree подготовлен основной Git-безопасный слой Vino:
  проектные правила, Agents OS, 6 ролевых профилей, требования, архитектура,
  scripts подготовки данных, contracts/registry, README и компактные summary.
- Интеграционный срез отправлен в `origin/codex/vino-integration`; основной
  commit содержимого — `42b5ee7`. GitHub предложил PR endpoint
  `https://github.com/ai-babai/brutforce/pull/new/codex/vino-integration`.
- Raw/media, закрытый PDF ТЗ, большие таблицы, Telegram-export, веса, индексы,
  архив Dataset и SSH credentials не добавлены в Git.
- В `.env.example` записаны только несекретные URL/имена моделей. Разница между
  предоставленными OCR/LLM/BGE-сервисами и обязательным visual retrieval
  зафиксирована в `docs/infrastructure/AI-SERVICES.md`.
- Проверка checkout разделена на `metadata-only` и `-FullData`, поэтому чистая
  Git-копия не требует приватных материалов для зелёного bootstrap.

## Проверки

- `scripts/verify-project-setup.ps1` — PASS: 6 agent-профилей, 18 источников,
  working memory 95 строк, внутренние Markdown-ссылки разрешаются.
- Все PowerShell-скрипты разобраны AST parser без ошибок.
- Все Python-скрипты проходят `compileall` через bundled Python runtime.
- Staged secret scan: private-key markers, non-placeholder Bearer credentials,
  GitHub/AWS token patterns не найдены.
- В наборе Git-изменений нет файлов больше 1 MiB; data archive остаётся вне Git.

## Серверная часть

Личный SSH key установлен только в локальный `.ssh`, в репозиторий не попадал.
Подключение не выполнялось: TCP/22 `sigma-ops` с текущего хоста не отвечает,
поэтому получить и сопоставить живой host key невозможно. Проверка host key не
отключалась. Команды на сервере не запускались, архив не передавался.

После восстановления маршрута порядок продолжения: сверить fingerprint,
прочитать живые `/srv/AGENTS.md` и `/srv/lct/AGENTS.md`, проверить диск и Git,
загрузить архив в новую `/srv/lct/data/roman/vino/2026-09-17/`, сверить SHA-256,
протестировать архив и только затем распаковать. Переданный через Telegram ключ
после использования требуется отозвать/заменить.

## Координационный пробел

Ветка доступна через Git, но карточка GitHub Project в этом проходе не создана:
`gh` отсутствует, а отдельная in-app browser session не авторизована в приватном
GitHub. Это не расширяет право обходить credential boundary; задачу следует
связать с карточкой при доступной авторизованной Project-сессии.
