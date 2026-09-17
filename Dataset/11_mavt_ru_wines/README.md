# 11_mavt_ru_wines

Versioned snapshot российских вин [МАВТ](https://mavt.ru/catalog/wine/) от
2026-09-15. Канонический `source_id` — `mavt-ru-wines-2026-09-15`, capture —
`mavt-capture-20260915`.

## Охват

- официальный wine-сегмент sitemap: 4 780 query-free product URL;
- проверено: 4 780/4 780, одна устаревшая ссылка перенаправляет на главную;
- подтверждено полем карточки `Страна: Россия...`: 763 SKU;
- точная связь SKU с декодируемым primary image: 760;
- у 3 SKU product image отсутствует, они находятся в `needs_annotation`;
- 2 SKU со значением `Россия (Винос де Мадрид)` находятся в
  `needs_verification` из-за противоречивой региональной части;
- реальных дополнительных gallery assets в HTML-шаблоне не найдено;
- 512 изображений рекомендаций, ошибочно загруженных широким gallery-pilot,
  сохранены в raw, но явно исключены через `tables/out_of_scope_images.jsonl`.

Региональная clean-категория сообщала 703 товара. Она использует запрещённую
robots query-pagination и не обходилась. Разница с 763 sitemap-карточками
объясняется более широким индексом sitemap и регионально-зависимой доступностью;
она не исправлена молча.

## Таблицы

- `tables/products.jsonl` — российские карточки и country evidence;
- `tables/catalog_memberships.jsonl` — точные product ID/артикулы МАВТ;
- `tables/media.jsonl` — только допустимые product images, дедуп по SHA-256;
- `tables/product_media_associations.jsonl` — связь image ↔ source SKU и роль;
- `tables/out_of_scope_images.jsonl` — полученные, но исключённые recommendation
  assets;
- `tables/crawl_errors.jsonl`, `tables/image_errors.jsonl` — учтённые сбои;
- `tables/SUMMARY.json`, `tables/AUDIT.json` — агрегаты и инварианты.

Целевая роль подтверждённых связей — `russian_open_world_reference`. Поля
`wine_family_id` и `label_design_id` не угадываются, `slug` «Своё Вино» не
назначается без отдельного exact identity review.

## Доступ и права

Discovery выполнен только через сохранённый официальный sitemap и canonical
`/catalog/id/<id>/`. Не использовались запрещённые `/filter/`, query-pagination,
cookies, ротация заголовков/IP или обход 403/429. Product images получены только
из явно разрешённого robots пути `/upload/`; watermark URL не запрашивались.

Открытая лицензия набора/изображений на сохранённых страницах не обнаружена.
Статус — `legal_review`: только внутреннее некоммерческое исследование до
юридической проверки, перераспространение raw запрещено без разрешения.

Воспроизведение:

```powershell
python scripts/dataset/crawl_mavt.py --interval 0.5 --workers 4
```

Crawler использует один `User-Agent: VinoDatasetResearch/1.0`, глобальный
интервал и немедленно останавливается при HTTP 403/429 или block-page marker.
