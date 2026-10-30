# Boost V16 C16

Действующий CPU recognition runtime Sigma PROD, зафиксированный 31.10.2026.
42 Python-файла перенесены побайтово с
`boost-independent-recovery-v16-c16-20261006`; их SHA находятся в
[`deploy/production.json`](../../../deploy/production.json).

`serve_v7.py` — реальный entrypoint, несмотря на историческое имя V7.
`v7_trace.py` связывает SIMPLE84 retrieval из `../boost/` с C16-уточнениями.
Модули `../parent/` дают неизменные detector/ONNX primitives.

Frozen Python и metadata не редактировать для «наведения красоты»:
runtime проверяет их SHA. Машинные пути и внешние файлы подготавливает
[`scripts/production-vision.py`](../../../scripts/production-vision.py).
В каталоге нет весов, reference vectors, OCR-данных и приватного gold.
Некоторые сохранённые docstring/metadata называют старые этапы C05/C08/V7;
фактическую версию определяют release metadata и production manifest.

Запуск, состав данных и границы проверки:
[`docs/PRODUCTION.ru.md`](../../../docs/PRODUCTION.ru.md).
