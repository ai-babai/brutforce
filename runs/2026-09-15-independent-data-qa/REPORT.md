# Независимый QA retail snapshots и master-index

Дата: 2026-09-15. Исполнитель QA работал read-only и не использовал сеть.

## Вердикт

- PASS
- P0: 0
- P1: 0
- P2: 0

## Проверено

- AMWine: 845 уникальных products/memberships, 1 760 media/associations;
  1 760/1 760 MIME заполнены (934 PNG, 638 WEBP, 188 JPEG), все изображения
  декодируются. `raw_files.jsonl` содержит ровно все 2 782 файла capture;
  missing/path/bytes/SHA mismatches — 0. Source AUDIT: 17/17.
- Master: 6 499 products, 6 499 memberships, 9 156 media, 11 005
  associations, 10 719 identity-eligible, 446 family candidates, 552
  verification и 3 annotation. MIME missing — 0; integrity — 18/18.
- Две associations AMWine из cross-product exact-duplicate группы имеют
  `identity_eligible=false`.
- МАВТ: 763/763 structured country evidence сохранили source value, page URL и
  64-hex SHA; перенесены 2 origin verification + 3 annotation задачи.
- Алкотека: перенесены все 58 grouped source tasks с actions/evidence/candidates;
  unsafe coverage — 64/64 product associations.
- Внешних присвоений `exact_current_svoe_slug` — 0.
- Повторная сборка master во временный каталог завершилась exit 0; все 9
  сгенерированных JSONL побайтно совпали с основным output. Временный каталог
  удалён.

## Исправления между проходами

Промежуточный QA находил P2 по MIME WEBP, двум неучтённым policy-status raw
files, потере structured origin evidence, отсутствующим decision logs,
противоречивым значениям страны МАВТ и потере source grouping Alkoteca. Все
замечания исправлены и повторно проверены.
