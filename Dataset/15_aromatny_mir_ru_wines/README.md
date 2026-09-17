# 15 — «Ароматный Мир»: российские вина

Версия набора: `1.0.0`
Дата snapshot: `2026-09-15`
`source_id`: `aromatny-mir-russian-wine-web`
`source_capture_id`: `amwine_20260915_001`

Robots-aware snapshot публичных карточек российских вин
[«Ароматного Мира»](https://amwine.ru/). Набор предназначен для open-world
библиотеки: наличие позиции на «Своём Вине» не требуется, а `svoe_slug` без
доказанного exact-match не присваивается.

## Состав

- 846 product URL прошли пересечение Russia country listings и официального
  product sitemap;
- 845 карточек разобраны, одна снятая позиция перенаправляет в категорию;
- все 845 карточек содержат точный внешний SKU и явное поле `Страна: Россия`;
- 1 760 gallery URL сохранены, 1 760 изображений декодируются и имеют явный
  MIME (включая 638 WEBP);
- 821 товар имеет изображения; 24 карточки без опубликованного JSON-LD image
  находятся в `review/needs_verification/queue.jsonl`;
- один и тот же primary image опубликован для двух SKU «Абрау-Дюрсо
  Классическое» — брют и полусухое; группа также направлена на проверку;
- 1 457 исходных image assets образуют 1 760 представлений, включая 303 группы
  с несколькими resize/gallery вариантами.

Сводка находится в `tables/SUMMARY.json`, машинные инварианты — в
`tables/AUDIT.json`. Полный provenance всех 2 782 raw-файлов хранится в
`tables/raw_files.jsonl`, product→image связи — в
`tables/product_media_associations.jsonl`, а catalog membership — в
`tables/catalog_memberships.jsonl`.

## Граница использования

Связь изображения с external SKU имеет `gold`-grade, когда URL опубликован в
JSON-LD конкретной карточки. `wine_family_id` остаётся пустым до межисточниковой
identity-проверки. `label_design_id` фиксирует байты primary image и не означает
автоматически подтверждённое семейство редизайна.

Это clean catalog reference, а не detection-набор. Bbox имеет статус
`not_applicable_clean_catalog_reference`; для multi-object detector изображения
не допускаются без отдельной аннотации. Цена и наличие относятся к выбранному
сайтом московскому магазину на момент snapshot.

Режим проекта некоммерческий, но права на обучение и производные остаются
`pending_terms_and_asset_rights_review`, перераспространение не подтверждено.

## Воспроизведение

```powershell
pythonw.exe scripts/dataset/crawl_amwine.py --image-mode all --delay 0.8 --workers 4
```

Crawler использует один описательный User-Agent, общий лимит начала запросов на
host и немедленный stop-event при HTTP 403/429. Cookies, private API, смена UA и
обход ограничений не используются.
