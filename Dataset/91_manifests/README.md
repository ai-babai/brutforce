# 91_manifests — происхождение и хеши

Имена предметных манифестов: `<source-id>-v<major>.<minor>.<patch>.jsonl`.
`raw-source-files-v1.0.0.jsonl` — файловый intake-манифест 15 непустых
source-контуров (9 219 файлов; ручная магазинная съёмка пока пустая). SHA-256
манифеста —
`baa306a1820f36c32fbcccf462dc57beda0696f0b9223816c45f2f21803ce524`.
Каждая строка содержит относительный путь, размер и SHA-256, но не
содержит закрытых URL, токенов, текстов сообщений или локальных абсолютных
путей.

Пересборка: `pwsh -File scripts/build-raw-source-manifest.ps1`. Для предметных
media records применяется [`../CONTRACT.md`](../CONTRACT.md).
