# Open-world master-index российских вин

Версия набора: `2026-09-15.1`.

Финальный snapshot содержит 6 499 отдельных source products, 9 156 ссылок на
media и 11 005 product→media associations. Из них 10 719 проходят identity
gate; 552 задач находятся в `needs_verification`, ещё 3 карточки МАВТ без
изображений — в `needs_annotation`.

Этот каталог агрегирует российские вина из уже разобранных источников, не
подменяя source identity общей догадкой. Каждая карточка магазина или набора
остаётся отдельным `master_product_id` и отдельным `catalog_membership`.

## Состав

- `tables/products.jsonl` — отдельные source product records с нормализованными
  полями производителя, бренда и названия;
- `tables/catalog_memberships.jsonl` — членство source product в конкретном
  snapshot каталога;
- `tables/media.jsonl` — ссылки на upstream media, SHA-256 и decode metadata;
- `tables/associations.jsonl` — явные связи source product ↔ upstream media;
- `tables/family_candidates.jsonl` — только provisional
  `same_family_uncertain`, полученные по точному нормализованному
  producer/brand + title;
- `review/needs_verification/queue.jsonl` — origin, ambiguous image identity и
  cross-source family candidates для ручной проверки;
- `review/needs_annotation/queue.jsonl` — source products, которым нужно добыть
  и подтвердить отсутствующее изображение;
- `tables/SUMMARY.json` — входные хеши, счётчики и машинные инварианты.

`vintage`, `volume_l`, `source_bottle_variant_id` и
`source_label_design_id` не схлопываются при создании family candidate. Даже
совпавшие кандидаты остаются разными продуктами до решения человека.

Поле `exact_current_svoe_slug` заполняется исключительно для ассоциаций
актуального снимка «Своё Вино», у которых исходный аудит подтвердил gold-связь
с изображением и допустимость exact SKU identity. Внешние источники не получают
этот slug по сходству текста или изображения.

## Media и права

Изображения сюда не копируются. `media.jsonl` хранит только provenance-ссылки
на канонические файлы исходных наборов. Допуск к обучению и распространению
нужно определять по `rights_status` исходного источника; наличие записи в
master-index не снимает legal gate.

## Воспроизведение

```powershell
python scripts/dataset/build_russian_wine_master.py
```

Сборщик детерминирован, атомарно перезаписывает производные JSONL и терпит
отсутствующие либо временно пустые retail outputs. Структурированное origin
evidence и группировка source review-задач сохраняются. Журналы решений
`review/verified/decisions.jsonl` и `review/rejected/decisions.jsonl` не
перезаписываются; решённые `review_item_id` исключаются из новой очереди.

Назначение train/validation/test этим проходом не выполняется.
