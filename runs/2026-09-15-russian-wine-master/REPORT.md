# Handoff VINO-006 — open-world master-index российских вин

- Результат: построен детерминированный агрегирующий слой
  `Dataset/18_russian_wine_master` поверх завершённых таблиц «Своё Вино»
  archive/live, X-Wines RU, Open Food Facts candidates, МАВТ, «Ароматного
  Мира» и Алкотеки.
- Данные/артефакты: версия `2026-09-15.1`; 6 499 отдельных source products,
  6 499 catalog memberships, 9 156 ссылок на upstream media и 11 005
  product-media associations. Из них 10 719 связей identity-eligible.
- Создано 446 provisional `same_family_uncertain` кандидатов; 324 пересекают
  каталоги. Автоматического cross-source merge нет, vintage, volume и label
  design не схлопываются.
- Очереди содержат 552 verification-задачи и 3 annotation-задачи. Source
  grouping сохранена: 53 placeholder + 5 shared-image групп Alkoteca, 24
  AMWine-карточки без media, одна AMWine cross-SKU duplicate-группа, две
  противоречивые origin-задачи МАВТ, 13 origin-задач OFF и 8 ambiguous
  live-связей «Своё Вино»; остальные задачи — family candidates.
- Slug gate: 2 033 текущих `exact_current_svoe_slug`; все они происходят только
  из проверенных gold live-associations. Внешним источникам slug не
  присваивался.
- Media gate: изображения не копировались. Все 9 156 media-записей имеют
  upstream relative path, SHA-256 и `decode_status=ok`; пути разрешаются внутри
  `Dataset`. Две AMWine exact-duplicate связи исключены из identity-eligible до
  review.
- Origin gate: структурированное evidence МАВТ сохраняет исходное значение,
  URL и SHA карточки. Две записи `Россия (Винос де Мадрид)` оставлены в source
  snapshot, но направлены в `needs_verification`.
- Проверки: `py_compile` — exit 0; два последовательных запуска builder — exit
  0; хеши всех основных outputs совпали; 18/18 integrity checks в
  `SUMMARY.json` равны `true`. Независимый финальный QA после исправлений:
  P0=0, P1=0, P2=0; temp rebuild побайтно совпал с основными outputs.

## Хеши основных артефактов

- `SUMMARY.json`: `69baca29731118a29e10460d457953f723cef0909140cbbedc736eb317a8353e`
- `products.jsonl`: `0242f0c6ae6857b625d3212f1688598c0d618cf3148757df7f5c554d200acb8b`
- `catalog_memberships.jsonl`: `ef4e29065f0639c1bab6c154ae570ecf632bf5d834da3112bf8e9e626ac0a8d7`
- `media.jsonl`: `0bb1e7cff527c5c754485b1e3af2bb6d2b8fa1b6a72b6fcf21c9b614350f7743`
- `associations.jsonl`: `a3f3b972ea9ebe198a4cf3a825059ecc3e33e1e63d44d02142f788aab5855898`
- `family_candidates.jsonl`: `3a6f7f42f1b9904dff5cd1fe4b4c965c2ae5267cfd0430e614a8d36f16e51e52`

## Не проверено

- Семантическая истинность 446 family candidates намеренно оставлена человеку.
- 13 OFF records ещё не подтверждены как российское производство.
- Права retail images остаются под source legal gate; некоммерческий режим не
  разрешает автоматически распространять raw или производные.

## Следующий шаг

Закрыть независимый QA, затем вручную разобрать source review и cross-catalog
family candidates до заморозки grouped split.
