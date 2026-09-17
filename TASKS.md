# Очередь работ Vino

Статусы: `ready`, `in_progress`, `blocked`, `done`, `superseded`.

## VINO-000 — Bootstrap проекта

- Статус: `done`.
- Результат: нормализовано ТЗ, создана навигация, Agents OS, память, роли,
  контракты данных и оценки, каталоги будущей реализации.
- Проверка: ссылки, TOML и структура должны пройти локальный bootstrap-check.
- Отчёт: `runs/2026-09-15-project-bootstrap/REPORT.md`.

## VINO-001 — Приём ресурсов кейса

- Статус: `done`.
- Владелец: `data_curator`.
- Вход: архив «Своё Вино», Telegram-export РВК, актуальный sitemap «Своё Вино»
  шесть внешних dataset-источников, три retail snapshots и четыре retail
  access-state получены либо проверены по применимости.
- Граница: `Dataset/00_raw/**`, `Dataset/01_...02_.../**`,
  `Dataset/91_manifests/**`, `Dataset/92_reports/**`, `docs/data/**`, отдельный
  `runs/<date>-data-intake/**`.
- Результат: исходники сохранены неизменяемо; зафиксированы SHA-256, размеры,
  формат, происхождение, права, schema profile и число объектов.
- Проверка: все файлы манифеста существуют, хеши пересчитываются, каждый объект
  имеет стабильный ID; секреты и закрытые URL отсутствуют в Git-документах.
- Выполнено: 15 непустых raw-контуров зафиксированы манифестом на 9 219 файлов;
  архивы безопасно распакованы, объектам назначены стабильные ID, построены
  item-level manifests, graded associations и quality reports. Актуальный wine
  sitemap разобран 2 041/2 041 без ошибок. Все принятые изображения и bbox
  учтены явным статусом; глобальный аудит проходит 34/34 проверки.
- Отчёт: `runs/2026-09-15-data-intake-audit/REPORT.md`.
- Зависимости: закрыты; ручные очереди переданы в VINO-002.

## VINO-002 — Аудит идентичности и near-duplicates

- Статус: `done`.
- Владелец: `data_curator` + независимый `qa_evaluator`.
- Результат: таблица соответствий `image_id/product_id/slug`, отчёт по дублям,
  конфликтам, отсутствующим фото и семействам визуально похожих этикеток.
- Проверка: выборочная ручная сверка и машинные инварианты уникальности.
- Выполнено: exact SHA-256 аудит 27 073 media-записей между источниками не
  нашёл пересечений; после подключения retail-наборов открыты 24
  межисточниковые same-dHash группы для повторной визуальной проверки;
  подготовлены очереди Telegram (207), ambiguous «Своё Вино» (61 + 8),
  RF100 cross-split dHash (33) и Open Food Facts origin review (13).
- Осталось: закончить ручную идентификацию и построить усиленный near-duplicate
  identity graph до фиксации split.

## VINO-003 — Frozen splits и baseline-контракт

- Статус: `blocked` до VINO-002.
- Владелец: `product_analyst` + `qa_evaluator`.
- Результат: versioned split manifest, leakage audit, зафиксированные метрики и
  политика изменения holdout.
- Проверка: один source/derivative/identity group не пересекает splits.

## VINO-004 — Первый CV retrieval baseline

- Статус: `blocked` до VINO-003.
- Владелец: `retrieval_engineer`.
- Результат: воспроизводимый index/query pipeline и отчёт top-1/top-5/F1/
  latency с анализом near-duplicate ошибок.
- Проверка: deterministic CPU smoke и отдельный GPU benchmark на frozen split.

## VINO-005 — Контракт end-to-end demo

- Статус: `blocked` до VINO-004.
- Владелец: `solution_architect` + `application_engineer`.
- Результат: versioned API schema и минимальный камера/галерея → `slug` →
  карточка с честным failure state.

## VINO-006 — Open-world библиотека российских вин

- Статус: `in_progress`.
- Владелец: `data_curator` + `qa_evaluator`.
- Вход: МАВТ, «Красное&Белое», ВинЛаб, SimpleWine; второй приоритет —
  «Ароматный Мир», Алкотека и LUDING.
- Результат: versioned snapshots российских карточек, изображения с точным
  source SKU, family/variant/design IDs и явной связью либо отсутствием связи со
  «Своё Вино».
- Проверка: robots/terms snapshot, polite crawl, decode/hash/accounting,
  country evidence, cross-source identity review и отсутствие forced slug-match.
- Выполнено: полностью обработаны доступные snapshots МАВТ (763 SKU, 760
  product images), «Ароматного Мира» (845 SKU, 1 760 gallery images) и Алкотеки
  (727 SKU/images, Краснодар). Построен master-index: 6 499 source products,
  9 156 media refs, 11 005 associations; 34/34 global checks и независимый QA
  P0/P1/P2=0. Для K&B/ВинЛаб/SimpleWine/LUDING сохранён blocked access-state,
  обход защиты не выполнялся.
- Осталось: получить официальный export/permission для четырёх защищённых
  источников и вручную закрыть 552 verification, 3 annotation и 24
  cross-source dHash задачи до frozen split.
- Зависимости: нет; может выполняться параллельно VINO-002.

## VINO-007 — Передача состояния и разбор командного onboarding

- Статус: `done`.
- Владелец: `product_analyst` + `data_curator`.
- Вход: текущее состояние Vino и локальный Telegram-export переписки с
  onboarding-пакетом BrutForce/Sigma от 2026-09-17.
- Граница: Telegram-export и вложенный архив только для чтения; изменения —
  `docs/transfer/**`, `runs/2026-09-17-colleague-intake/**`, воспроизводимый
  упаковщик и `artifacts/transfer/2026-09-17/**`.
- Результат: безопасный metadata/code handoff без raw/media/secrets и оценка
  поручений, зависимостей, противоречий и рисков командного onboarding.
- Проверка: manifest с SHA-256 каждого файла, content/filename secret scan,
  тест целостности архива и отдельный SHA-256 архива; закрытый SSH-ключ не
  извлекается и не попадает в проектные артефакты.
- Выполнено: составлен отчёт по задачам, конфликтам и рискам; подготовлен
  разбор onboarding. Первоначальный metadata/code archive признан неверным по
  составу после уточнения пользователя и заменён data-only пакетом VINO-008.
  GitHub-приглашение принято пользователем; 2026-09-17 локальный Git-доступ
  аккаунта `MisterMolox` к приватному репозиторию проверен чтением remote refs.
- Отчёт: `runs/2026-09-17-colleague-intake/REPORT.md`.
- Зависимости: перед реальным SSH-onboarding владелец инфраструктуры должен
  отозвать переданный приватный ключ и выдать новый безопасным способом либо
  добавить публичный ключ участника.

## VINO-008 — Архив распарсенного датасета для команды

- Статус: `done`.
- Владелец: `data_curator`; приёмка — `qa_evaluator`.
- Вход: `Dataset/01_...18_...`, review/split/manifests/reports и media/PDF,
  на которые ссылаются нормализованные таблицы.
- Граница: data-only package; проектный код, `agents-os`, исходное ТЗ и
  нереференсный `Dataset/00_raw` не включаются.
- Результат: самодостаточный 7z с распарсенными таблицами, изображениями,
  bbox/labels, review queues и выбранными raw media dependencies при сохранении
  исходных относительных путей; напрямую referenced cache-media сохраняются,
  прочие cache-файлы исключаются.
- Проверка: каждый включённый файл имеет path/bytes/SHA-256; все media refs
  разрешаются; `7z t`, внешний SHA-256, проверка состава и независимый QA.
- Выполнено: 32 883 manifest-файла и 2 package metadata упакованы в data-only
  архив 3 982 310 819 байт. Все 37 650 path-значений разрешаются; независимый
  QA — PASS, P0/P1/P2=0.
- Отчёт: `runs/2026-09-17-dataset-transfer/REPORT.md`.
- Зависимости: пакет предназначен только для внутреннего некоммерческого
  исследования; права и ограничения распространения сохраняются по источникам.

## VINO-009 — Интеграция Vino в BrutForce и серверная поставка Dataset

- Статус: `in_progress`.
- Инициатор: Роман.
- Владелец: `solution_architect` + `data_curator`; приёмка — `qa_evaluator`.
- Граница Git: правила, память, требования, архитектурные документы, dataset
  contracts/README/summary и воспроизводимые scripts; raw/media/закрытое ТЗ,
  большие таблицы, токены и ключи исключены.
- Граница сервера: отдельная ветка/worktree; архив Dataset размещается вне Git в
  `/srv/lct/data/roman/vino/2026-09-17/` и распаковывается только в новую
  версионированную папку после проверки хеша.
- Результат: Vino является основной проектной основой BrutForce; Git-ветка
  доступна команде; data-only пакет загружен, его SHA-256 и manifest validation
  подтверждены на сервере.
- Проверка: secret/large-file scan, проверка ссылок и layout, review diff;
  `git push`; на сервере — `sha256sum`, тест архива, свободное место и сверка
  количества/хешей по package manifest.
- Выполнено: Git-безопасный импорт отправлен в
  `origin/codex/vino-integration`; серверный worktree создан в
  `/srv/lct/work/vino-integration`. Архив 3 982 310 819 байт загружен в
  `/srv/lct/data/roman/vino/2026-09-17/`, `7z t` и SHA-256 прошли. После
  распаковки проверены 32 883 manifest-записи / 4 205 228 981 байт, ошибок 0;
  всего в `Dataset/` 32 885 файлов, `current` указывает на эту версию.
- Проверка доступа: live ED25519 host fingerprint совпал с onboarding-пакетом;
  вход личным ключом Романа подтверждён как `lct@sigma-ops`. Проверка host key
  не отключалась.
- Осталось вне этой задачи: создать/принять PR в `main` и ротировать приватный
  ключ, который ранее передавался через Telegram.

Новые задачи добавляются только с наблюдаемым результатом, владельцем,
границей файлов, проверкой и зависимостями.
