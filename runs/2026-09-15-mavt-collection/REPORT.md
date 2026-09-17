# Handoff VINO-006 — МАВТ

- Результат: создан полный robots-aware snapshot wine-сегмента sitemap МАВТ от
  2026-09-15. Проверено 4 780/4 780 canonical product URL; 763 карточки имеют
  явное `Страна: Россия...`, 760 из них связаны с декодируемым primary image.
  Три карточки без product image поставлены в `needs_annotation`.
  Две карточки со значением `Россия (Винос де Мадрид)` поставлены в
  `needs_verification` как противоречивое origin evidence.
- Source IDs: `mavt-ru-wines-2026-09-15`,
  `mavt-capture-20260915`.

## Изменённые файлы

- `scripts/dataset/crawl_mavt.py` — resumable sitemap crawler, parser,
  image downloader, manifests, review queues и integrity gates.
- `Dataset/00_raw/11_mavt_ru_wines/2026-09-15/**` — неизменённые response
  bodies, безопасные headers, checkpoints и raw manifests.
- `Dataset/11_mavt_ru_wines/README.md` — охват, структура, права и запуск.
- `Dataset/11_mavt_ru_wines/tables/**` — products/media/memberships/
  associations/errors/summary/audit.
- `Dataset/11_mavt_ru_wines/review/**` — 3 задачи `needs_annotation`.
- `runs/2026-09-15-mavt-collection/REPORT.md` — этот handoff.

## Данные и артефакты

- Raw: 2 051 файл, 97 343 953 bytes.
- Derived: 763 продукта, 763 membership, 760 media, 760 exact primary
  associations.
- `crawl_manifest.jsonl`: 4 780 строк, SHA-256
  `ab9aa45e7375a1ff5bbd4c3ffb260c95bd0b1b6e754f4937f21b772500f15acb`.
- `image_manifest.jsonl`: 1 272 строки, SHA-256
  `8b807bba97f18307f5083eea362bf27bcf96ee40f1c1a3287c210b1dc04c4517`.
- `products.jsonl`: SHA-256
  `7754f0cdbe1b1e38d87e8ededf905da367512a1ee6c76f1c71597a7fa4e8746c`.
- `media.jsonl`: SHA-256
  `c417d19112600df157d4ffd55b35b43374ec8a8d4d9b02a674c805bae9d0f3d9`.

Почему raw image URL больше eligible media: первый широкий gallery-pilot нашёл
1 272 допустимых `/upload/` URL внутри Bitrix component-root. Ручной DOM QA
показал, что 512 из них принадлежат блоку «Похожие товары», а не галерее
текущего SKU. Raw bytes сохранены, но все 512 получили
`out_of_scope_recommendation_or_non_product_asset` и исключены из products,
media и associations. В product presentation фактически осталось 760 primary
URL; дополнительных разрешённых gallery URL не найдено. Watermark endpoint
запрещён robots и не запрашивался.

## Проверки

- Полный run:
  `python scripts/dataset/crawl_mavt.py --interval 0.5 --workers 4` — exit 0.
- Syntax:
  `python -m py_compile scripts/dataset/crawl_mavt.py` — exit 0.
- Независимый PowerShell audit — exit 0: 763/763 уникальных product/external
  IDs, 0 foreign country rows, 0 broken memberships/associations, 0 media/page/
  raw-image SHA-256 mismatches, 0 decode errors.
- Anti-bot gate: 0 HTTP 403/429, `STOP.json` отсутствует; один UA, без cookies,
  IP/header rotation и query/filter crawl.

## Не проверено

- Cross-source `wine_family_id`, vintage/redesign и exact-match со «Своё Вино».
- Семантический визуальный review всех 760 этикеток; проверены source association,
  country evidence, decode/hash и DOM-границы.
- Права на обучение/производные/распространение: открытая лицензия не найдена.

## Риски и допущения

- Clean regional category показывает 703 товара, sitemap дал 763 российских
  карточки; вероятная причина — региональная доступность и более широкий индекс.
- Одна sitemap-ссылка (`608986`) устарела и ведёт на главную; она учтена как
  parse error и не принята.
- Права имеют статус `legal_review`; raw redistribution запрещён без разрешения.

## Следующий шаг

`data_curator` + независимый `qa_evaluator`: вручную закрыть 3 missing-image SKU
и затем построить cross-source family/variant/design matching с приоритетом
ребрендингов и соседних винтажей, не назначая `slug` без exact evidence.
