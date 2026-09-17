# Источники open-world библиотеки российских вин

Дата snapshot/audit: 2026-09-15. МАВТ, «Ароматный Мир» и Алкотека собраны в
разрешённых границах; четыре других источника остановлены на access gate.
Это не разрешение на повторный неограниченный crawl. HTML/JSON и изображения
сохраняют отдельные права использования.

| Приоритет | Источник | Наблюдаемая ценность | Технический gate |
|---|---|---|---|
| 1 | [МАВТ](https://mavt.ru/catalog/wine/) | 763 российских SKU; 760 exact primary images | 4 780 sitemap URL проверены; faceted/query URL не запрашивались; 3 missing-image + 2 origin review |
| 1 | [Алкотека](https://alkoteka.com/catalog/) | 727 российских SKU/images в Краснодаре | публичный API snapshot завершён; 663 identity-eligible, 58 grouped review tasks |
| 1 | [SimpleWine](https://simplewine.ru/catalog/vino/filter/country-rossiya/) | 326 российских вин, числовой ID, винтаж и подробные атрибуты | declared research UA получил 403 уже на robots; нужен официальный export/permission |
| 2 | [Красное&Белое](https://krasnoeibeloe.ru/catalog/__2/) | отдельная категория «Вино Россия», массовый ассортимент и уникальные SKU | robots и sitemap получены, `Crawl-delay: 2`; product page вернул 403 — нужен export/permission, обход запрещён |
| 2 | [ВинЛаб](https://www.winelab.ru/) | article, бренд, производитель, страна, регион, винтаж и несколько изображений | sitemap содержит 3 027 URL, но product page вернул 401; robots ограничивает `/medias/` — metadata только из разрешённого export |
| 2 | [Ароматный Мир](https://amwine.ru/) | 845 российских SKU; 1 760 gallery images | sitemap/card snapshot завершён; 24 missing-image cards + 1 cross-SKU duplicate group в review |
| 3 | [LUDING](https://luding.ru/) | 9 876 вин, богатая семантика и российские производители | declared research UA получил 403 на robots; городские поддомены создают дубли, предпочтителен export/официальный PDF/API |

Второй эшелон после этих pilots: [Винотека](https://vinotheque.ru/) — публичный
sitemap, но `Crawl-delay: 20`; а также официальные каталоги российских
производителей (Абрау‑Дюрсо, Фанагория, Кубань‑Вино, Мысхако, Сикоры,
Шато де Талю). Производитель часто является лучшим источником истории винтажей и
редизайна, чем текущая розничная витрина.

## Что извлекаем

Обязательно: source SKU/article, canonical URL, capture time, название,
производитель, бренд/линейка, страна производства, регион, винтаж, объём, цвет,
сахар, сортовой состав, все оригинальные image URLs и их SHA-256. Цена и остаток
хранятся только как snapshot metadata и не участвуют в identity.

Каждая карточка сначала получает внешний `product_id`; crosswalk со «Своё Вино»
выполняется отдельно. Совпадение имени недостаточно: exact match требует
совместимых производителя, линейки, винтажа/варианта, объёма и визуального
дизайна. Несовпавшее российское вино остаётся в `russian_open_world_reference`.

## Правило следующего capture

1. Сохранить robots, terms, sitemap и заголовки ответа как raw snapshot.
2. Начинать с малого pilot и расширять только после проверки access response и
   качества source association.
3. Проверить decode, SHA-256, source SKU, полноту country/vintage и image rights.
4. Построить cross-source candidates, затем вручную проверить редизайн/винтаж.
5. Только после отчёта расширять crawl; при 401/403/429 не обходить защиту.

Текущий результат сведён в `Dataset/18_russian_wine_master`; K&B, ВинЛаб,
SimpleWine и LUDING требуют официального export/permission.
