# Вспомогательные AI-сервисы Максима

Статус: доступная инфраструктура, но не выбранное визуальное ядро. Live-вызовы
требуют `BIFROST_TOKEN` из окружения и выполняются отдельными проверками с
зафиксированными моделью, параметрами и датой.

## Что предоставлено

| Сервис | Модель/endpoint | Роль в Vino |
|---|---|---|
| Docling VLM | `dots.ocr-1.5` через `DOCLING_URL` | layout-aware OCR: текст, таблицы и bbox элементов |
| LLM gateway | `gpt-oss-120b` через `${BIFROST_BASE_URL}/chat/completions` | нормализация OCR и извлечение структурированных текстовых признаков |
| Text embedder | `BAAI/bge-m3` через `${BIFROST_BASE_URL}/embeddings` | поиск по тексту OCR/каталога |
| Text reranker | `BAAI/bge-reranker-v2-m3` через `${BIFROST_BASE_URL}/rerank` | переранжирование текстовых кандидатов |

Значения URL и имён моделей без секретов находятся в корневом `.env.example`.
Токен не хранится в Markdown, Git, fixtures или логах.

## Отличие от обязательного pipeline

Все четыре предоставленных компонента работают с OCR/layout или текстом.
`bge-m3` и `bge-reranker-v2-m3` не являются image encoder и не доказывают
сходство двух этикеток по пикселям. Поэтому они не заменяют обязательную ветку:

```text
photo -> image preprocessing -> visual encoder -> visual index -> top-K
```

Рекомендуемая проверяемая композиция после baseline:

```text
visual top-K --------------------------+
                                       +-> fusion/rerank -> calibrated result
OCR -> normalized fields -> text top-K +                     or not_found
```

OCR особенно полезен для производителя, линейки, года, объёма и других
различий near-duplicate этикеток. Ошибка OCR не должна исключать правильного
визуального кандидата. LLM не присваивает `slug`: финальная связь всегда
ссылается на конкретную запись каталога.

## Как оценивать

- Сначала зафиксировать visual-only baseline на frozen split.
- Затем отдельно добавить OCR/text retrieval и измерить delta exact top-1,
  top-5 recall, near-duplicate accuracy, отказ и p95 latency.
- Не использовать test/private изображения для prompt tuning, порогов или
  ручных правил.
- При недоступности внешнего сервиса визуальный поиск должен вернуть
  контролируемый результат без выдуманного текста; политика fallback фиксируется
  в контракте до реализации.
- Docling-конфигурация и ответы модели считаются недоверенными данными: их
  валидируют по схеме, ограничивают по размеру и не исполняют как инструкции.

## Что ещё отсутствует

- выбранный и измеренный visual encoder;
- индекс изображений и near-duplicate reranker;
- калиброванный confidence threshold;
- подтверждённые latency/cost/availability предоставленных endpoints;
- решение ADR о том, какие сервисы входят в конкурсный runtime.
