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
Live ED25519 fingerprint `sigma-ops` совпал с onboarding-пакетом; вход ключом
Романа подтверждён как пользователь `lct`. Проверка host key не отключалась.
Исходный timeout был вызван маршрутизацией SSH через NL VPN; для соединения
использован прямой интерфейс, не изменяющий остальной VPN-трафик.

- Worktree: `/srv/lct/work/vino-integration`, ветка
  `codex/vino-integration`, commit `dfe3878` на момент поставки.
- Архив: `/srv/lct/data/roman/vino/2026-09-17/` — 3 982 310 819 байт,
  SHA-256 `a3bc9d8bd6d8b1524a46354b4c8f1bb7a7d06964c9dd17325a07b8b22809b8d8`.
- `7z t` — PASS; распаковано 32 885 файлов.
- Перепроверены SHA-256/размеры всех 32 883 manifest-файлов общей величиной
  4 205 228 981 байт; ошибок 0. Manifest SHA-256 совпал с package summary.
- `/srv/lct/data/roman/vino/current` указывает на `2026-09-17`; после поставки
  на сервере свободно 190 ГБ.

Переданный через Telegram приватный ключ после использования требуется
отозвать/заменить.

## Координационный пробел

Ветка доступна через Git, но карточка GitHub Project в этом проходе не создана:
`gh` отсутствует, а отдельная in-app browser session не авторизована в приватном
GitHub. Это не расширяет право обходить credential boundary; задачу следует
связать с карточкой при доступной авторизованной Project-сессии.
