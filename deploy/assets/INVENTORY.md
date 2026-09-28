# F8 CPU · фактический asset inventory (28.09.2026)

Источник: чтение active TEST unit и файлов на Sigma; базовая привязка в
`deploy/f8-runtime.json`. Список **точных байтов**, включая родительские imports,
процессор, ONNX, индекс, OCR-языки и 3 HF snapshots: [f8-cpu.sha256](f8-cpu.sha256).
Это манифест комплекта для офлайн-переноса, не лицензия на публикацию самих файлов.

| Состав | Версия / назначение | Статус распространения |
|---|---|---|
| `overlay/*` | F8 `F8-CPU-text-confirmed-rescue-P4-diagnostic-v1`; lexicon, organizer allowlist (2103 slug), visual-neighbors (TEST default; override ниже) | Авторство/право публичного распространения overlay, lexicon и каталожных производных **pending**. Не коммитить байты. |
| `parent/*.py` | 16 источников из установленного F0; F8 прямо проверяет SHA восьми ключевых модулей | Происхождение и право redistrib **pending**, нужная авторская ревизия не установлена. |
| `onnx/*` | FP32 SO400M vision ONNX 1 713 332 860 байт, tokenizer/processor и parity record | [Исходная модель](https://huggingface.co/google/siglip2-so400m-patch16-384) указывает Apache-2.0; соответствие производного экспорта/атрибуция **pending**. |
| `index/*`, `catalog/catalog-bundle.json` | organizer-catalog-20260919, index `so400m384-owlv2-v2-crops-reference-gated-20260925`; 2103 references, SHA каталога `a52c6a...4f677b2` | Конкурсные reference metadata и индекс **только авторизованный offline transfer**, публичный доступ pending. Gold/фотографии запросов в комплект не входят. |
| `models/hub/*` | [RT-DETR](https://huggingface.co/PekingU/rtdetr_r18vd) `@ac77a11ff0170a41b771c03264987f8ce2b0d753`, [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) `@cfd3195ba4ea9592eec887ded089f4c08eff231d`, [SigLIP2 Base](https://huggingface.co/google/siglip2-base-patch16-224) `@75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | Все три HF карточки на 28.09 указывают **Apache-2.0**, public/ungated; при распространении сохранить лицензию/NOTICE/атрибуцию. SHA карточек из API совпадают с revision в кеше. |
| `ocr/*` | TEST Tesseract `5.5.0`, binary SHA `644efa639b77a21b1096a6ced155112f0c730d05c7db871d52f4b2eb16bdf42a`; `rus.traineddata` SHA `e16e5e...df225`, `eng.traineddata` SHA `7d4322...170b2` | TEST packages `tesseract-ocr 5.5.0-1build1`, `tesseract-ocr-rus/eng 1:4.1.0-2build1` (Ubuntu). Языковые байты в read-only bundle; лицензии пакетов проверить до публичного распространения. Bookworm apt Tesseract отличается либо **unknown** до сборки; OCR-паритет pending. |
| `deploy/assets/vision-requirements.txt` | Python 3.12, torch 2.8.0+cpu, torchvision 0.23.0+cpu, transformers 4.57.6, onnxruntime 1.24.4 и pinned транзитивные пакеты | Третьи стороны: лицензии в metadata/wheels, отдельная публикационная проверка **pending**. |
| Приложение | Git `d26afa3` в этом checkout, `apps/api/go.sum`, `apps/web/package-lock.json` | Собственный код; право раскрытия согласовывает владелец. |
| Docker base | node 22.19.0 `4a4884e8...02b90`, Go 1.23.12 `167053a2...614db`, Python 3.12.11 `519591d6...57bf7`, Debian bookworm-slim `3783cc01...6251`, PostgreSQL 18.6 `3725f4e2...6650` | Multiarch OCI SHA закреплены непосредственно в Dockerfile/Compose (Docker Hub tag API, 28.09). Apt `libgomp1`/`tesseract-ocr` и wheel lock по SHA ещё **pending** без clean Linux image build. |
| Display package/media | `catalog-release-1` версия `svoe-20260927-alpha-2035-v1`: manifest SHA `d88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef`; `wines.jsonl`, `aliases.json`, `catalog.json`, `internal/display-policy.json`, `PREPARATION.md` и media `400/800/original` вне Git | SHA получен у владельца выпуска; содержимое/media проверяет importer. Публичные права **pending**; не путать с `catalog-bundle.json`. |
| TEST recommendations override | `display-text-attributes-winery-review-v2`, SHA `f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f` | Подтверждён владельцем TEST после data-change. Доставлять отдельно read-only; `overlay/visual-neighbors.json` остаётся F8 snapshot, но **не** активный index рекомендаций. Публичные права **pending**. |

Перенос без приватных путей в репозитории (Python 3.12+):

1. Оператор с правом доступа готовит **вне checkout** JSON `source-map.json` с ключами
   `overlay`, `parent`, `onnx`, `index`, `catalog`, `models`, `ocr`. Значения — пути к
   соответствующим каталогам; `models` указывает на HF `hub/` со snapshots,
   `ocr` — на каталог с русским и английским `*.traineddata`.
   Источник допускается получать с доверенного хоста или из разрешённого архива.
2. На доверенном хосте: `python3 scripts/asset-bundle.py export --sources /private/source-map.json --out /private/f8-bundle`.
   Копируются **только** зафиксированные файлы, HF symlinks разворачиваются в
   обычные файлы, сверяются SHA; при несовпадении export прекращается.
3. Перенести каталог `/private/f8-bundle` по разрешённому приватному каналу на
   Linux, затем `python3 scripts/asset-bundle.py verify /private/f8-bundle`.
   Веса никогда не включаются в Docker build context, а монтируются `:ro`.
4. Для display и рекомендаций подготовить отдельно immutable release package и
   approved recommendation index; сравнить slug/ID и обновить переменные
   `CATALOG_VERSION`, `RECOMMENDATION_INDEX_SHA256` перед импортом/запуском.
   Не включать их в Git или bundle F8 без разрешения владельца.

`f8-cpu.sha256` описывает файлы распознавания, **не** снимок всех внешних
каталожных WebP и не release controller/policy. Недоступность этих байтов или
неподтверждённые права обозначают pending clean Linux/parity. Прогрев F8,
наличие OCR-языков и паритет на отдельной машине проверяются против тех же SHA;
точный binary OCR 5.5.0 пока не упакован. Sigma не является
местом для третьей ML-копии.
