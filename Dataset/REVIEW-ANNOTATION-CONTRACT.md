# Review и annotation contract

Версия: `1.0.0`
Дата: 2026-09-15

## Зачем

Неоднозначное изображение не удаляется и не получает ближайший правдоподобный
label. Оно остаётся доступным по `media_id` и попадает в одну из двух рабочих
очередей: проверка идентичности или полная разметка.

## Структура каждого набора

```text
NN_source/
  media/                         # канонические производные, не двигаются
  tables/                        # manifests и associations
  review/
    needs_verification/queue.jsonl
    needs_annotation/queue.jsonl
    verified/decisions.jsonl
    rejected/decisions.jsonl
    STATUS.json
```

`queue.jsonl` — воспроизводимое представление нерешённых задач. Решения человека
добавляются в `decisions.jsonl`; генератор очередей никогда не перезаписывает
эти журналы. Копии изображений в `review/` запрещены.

## Состояния

| Состояние | Значение | Допуск |
|---|---|---|
| `needs_verification` | есть кандидаты, но не доказана identity/origin/variant | только unsupervised или excluded |
| `needs_annotation` | сцена полезна, но нет полного перечня объектов и bbox | excluded из supervised |
| `verified` | решение подтверждено с evidence и reviewer | по разрешённым `training_uses` |
| `rejected` | объект/связь опровергнуты или непригодны | excluded; raw не удаляется |

Минимальная queue-запись: `review_item_id`, `source_dataset`, `review_state`,
`media_id` либо `product_id/group_id`, `required_action`, `evidence` и список
кандидатов. Решение дополнительно содержит `decision`, `reviewer`,
`reviewed_at`, `evidence_refs` и версию инструкции.

## Идентичность вина и редизайн

- `wine_family_id` объединяет одно кюве/линейку вне зависимости от года и
  дизайна.
- `product_id` — нормализованная товарная сущность внутри нашего knowledge
  graph; она может существовать без «Своё Вино».
- `bottle_variant_id` фиксирует различимый год, объём и исполнение бутылки.
- `label_design_id` объединяет одинаковое поколение дизайна этикетки.
- `catalog_membership` связывает variant с конкретным snapshot и внешним SKU.

Связи между вариантами получают тип: `exact_variant`, `same_wine_new_vintage`,
`same_wine_rebrand`, `same_family_uncertain` или `different_product`. Для
closed-set ответа допустим только `exact_variant` с проверенным `slug` текущего
snapshot «Своё Вино».

## Роли в обучении

- `svoe_closed_set_reference` — точный SKU и slug текущего каталога.
- `russian_open_world_reference` — подтверждённое российское вино любого
  каталога с точным source SKU.
- `variant_hard_negative` — то же семейство, но другой винтаж/редизайн/вариант.
- `unknown_to_svoe` — российское вино без exact match в текущем «Своё Вино».
- `scene_detection_only` — bbox бутылки известен, SKU нет.

Одна запись может иметь несколько разрешённых ролей. Назначение train/val/test
остаётся только в `90_splits`, с группировкой по family/variant/design и
источнику производной.
