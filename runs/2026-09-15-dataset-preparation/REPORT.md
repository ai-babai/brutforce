# VINO-001 — подготовка Dataset

Дата: 2026-09-15
Статус: структура и raw intake готовы; item-level parsing остаётся в работе.

## Результат

- Старый локальный корень `data/` перенесён в единый `Dataset/`.
- Исходный `Датасет.zip` и каталог Telegram-export перемещены в `00_raw` без
  изменения содержимого.
- Созданы нумерованные контуры `01`–`10`, frozen splits, manifests, reports и
  quarantine.
- Зафиксированы контракт идентичности, graded photo/product associations,
  leakage rules и раздельные статусы прав.
- Проект явно отмечен как `noncommercial_research`.
- Внешние кандидаты зарегистрированы и оценены, но не скачаны.
- Создан raw file manifest на 562 записи; SHA-256 manifest:
  `8ba9c2363ec39c2fac58d096985e2ef8a108d48983e5f2b0ac4075e87f3e0662`.

## Проверенные исходники

| Источник | Размер/число | Якорный SHA-256 |
|---|---:|---|
| «Своё Вино» | 2 252 013 652 байта | `b01a1b9…d92f8` |
| Telegram РВК | 561 файл, 69 596 925 байт | `messages.html`: `b54b4037…04dde` |

Подробный профиль: [`../../Dataset/92_reports/INTAKE-PROFILE-2026-09-15.md`](../../Dataset/92_reports/INTAKE-PROFILE-2026-09-15.md).
Оценка внешних источников: [`../../docs/data/EXTERNAL-DATASETS-ASSESSMENT.md`](../../docs/data/EXTERNAL-DATASETS-ASSESSMENT.md).

## Команды воспроизведения

```powershell
pwsh -NoProfile -File scripts/build-raw-source-manifest.ps1
pwsh -NoProfile -File scripts/verify-dataset-layout.ps1 -FullHash
pwsh -NoProfile -File scripts/verify-project-setup.ps1
```

## Gate

`Dataset/90_splits/v1` оставлен пустым намеренно. Назначать train/val/test до
item-level IDs, association audit и perceptual dedupe запрещено.

## Фактическая проверка

- `verify-dataset-layout.ps1 -FullHash`: PASS; 10 источников, 562 manifest
  records, пересчитаны все файловые SHA-256.
- `verify-project-setup.ps1`: PASS; структура, Markdown-ссылки, 6 custom-agent
  profiles и лимит рабочей памяти согласованы.
- `REGISTRY.yaml`: разобран YAML-парсером; `commercial=false`, 10 sources.
- `SPLIT-CONTRACT.yaml`: разобран YAML-парсером; доли development pool
  `0.70/0.15/0.15`, assignment заблокирован до identity audit.
- Поиск ссылок на каталоги прежнего корня данных: совпадений после обновления
  нет.

`F:\projects\Vino` пока не инициализирован как Git repository. Правила
`.gitignore` подготовлены, но фактическое отсутствие raw среди tracked files
можно проверить только после отдельного `git init`/подключения репозитория.

## Следующий шаг

Воспроизводимо распарсить каталог и Telegram в `01_...`/`02_...`, не изменяя
raw; затем провести `VINO-002` и только после него заморозить split v1.
