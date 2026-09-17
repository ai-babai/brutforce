# Handoff VINO-006 — retail-источники российских вин

## Результат

Полностью собраны доступные на 2026-09-15 robots-aware snapshots:

- МАВТ: 4 780/4 780 sitemap-карточек проверено, 763 российских SKU, 760
  точных primary images; 3 карточки без изображения, 2 противоречивых origin
  values в review;
- «Ароматный Мир»: 845 российских SKU, 1 760/1 760 gallery images, 1 760
  точных associations; 24 карточки без media и одна cross-SKU exact-image
  группа в review;
- Алкотека: 727 российских SKU/images для фиксированного контекста Краснодара,
  663 identity-eligible; 53 placeholder и 5 shared-image групп в review.

Итого новые retail snapshots: 2 335 отдельных source SKU и 3 247 media records.
Единый open-world master-index содержит 6 499 source products, 9 156 media refs,
11 005 associations и 10 719 identity-eligible associations. Внешним источникам
не присваивался `slug` «Своё Вино».

## Ограниченный доступ

- K&B: robots и root sitemap сохранены; следующая product-карточка ответила 403.
- ВинЛаб: robots и sitemap на 3 027 URL сохранены; product-карточка ответила 401.
- SimpleWine и LUDING: robots probe ответил 403.

После 403/401 сбор останавливался. Не применялись смена UA/IP, cookies, private
API или обход защиты. Для product-level данных этих четырёх источников нужен
официальный export либо разрешение владельца.

## Качество и права

- Глобальный dataset audit: 34/34 PASS.
- Независимый финальный QA: P0=0, P1=0, P2=0.
- Cross-source exact SHA groups: 0 среди 27 073 media rows.
- Same-dHash: 24 группы оставлены в ручной review; это кандидаты, не доказанные
  дубликаты.
- Все raw-контуры: 9 219 файлов, manifest SHA-256
  `baa306a1820f36c32fbcccf462dc57beda0696f0b9223816c45f2f21803ce524`.
- Некоммерческий режим не отменяет source rights gate: retail images остаются
  `pending_terms_and_asset_rights_review`, raw redistribution не подтверждено.

## Следующий шаг

Получить exports/permission для K&B, ВинЛаб, SimpleWine и LUDING. Параллельно
закрыть 552 master verification, 3 annotation и 24 cross-source dHash задачи до
заморозки grouped `train/val/test` split.
