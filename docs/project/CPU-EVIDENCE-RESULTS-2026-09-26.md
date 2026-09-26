# ML-083 · CPU evidence: независимая оценка

Статус на 17:22 МСК: frozen 213 кандидата измерены; organizer остановился на 84/103 ради доступности demo, runner завершился по независимому лимиту. Общий gate не подтверждён, rerank не выпущен в приложение.
Исходный commit worktree: `b3cd0ba9866c7ae7c96a5a938b99a15797cb0332`.
Приёмка заранее зафиксирована в [PLAN](PLAN.md), строки 303–332.

## Контроль на 14:05 МСК

- Публичные входы: `/Users/skif/ml-data/brutforce/night-20260925/cpu/public-v2.json`
  (213; SHA-256 `cee45789da9e10deb6426a17338583eba2ce1688ef76a6df32f4f0e9aef22f20`)
  и `organizer-public.json` (103, 100 уникальных SHA; SHA-256
  `396a66f0ac4d70c88598259aab76ce39087462777d571246b9774a53dccf4b3d`).
  На Sigma runtime-исполнитель указал `/srv/lct/data/vision-service/benchmarks/night-20260925-cpu/`.
- Исторические полные ответы ORT6: `cpu/raw/ort6-eval-http.jsonl` (SHA-256
  `4e61a9c755b534a96bfabe3b3292f318e29f489d7e9372b68a7d99537cd23567`)
  и `cpu/raw/ort6-organizer-http.jsonl` (SHA-256
  `739054b5dbc88b218c9a70d70938ac15112a64dab331eeb5937f6544099a8247`).
  Версия графа/индекса/настроек: `cpu/runtime-provenance-lock.json` (SHA-256
  `5280385c5f509326a10627e672fb89fb8ca485c1468f743c1ffc6dbc798381da`).
- Доверенный gold v2: `cpu/.scorer/gold-v2.json` (SHA-256
  `ad4534eb2a1f3bf14a26e5d78d5af2f1195a0ce29e11f19f27bf12a3853a4510`). Исправленные внутренние
  метки organizer: `vision-retrieval-20260925/annotation/sealed-v1.jsonl`
  (SHA-256 `f0362a9ebf6e2060148c401799c0bcba299b4f56a294b15ec219f6368e2b2589`)
  и `absence-audit/parent-accepted-overlay-v1.json` (SHA-256
  `1f225185848441098eb5dbe9bdc8013b67a10d250db6b8fe94e0fecb4f0ed21f`).
  Private gold и детальный ответ на каждый кадр остаются вне Git и inference-хостов.

Прогон scorer «ORT6 против самого себя» подтвердил контроль: 110/141 graded service,
56/62 retrieval Top-1, 19/22 `no_match`, 0/10 `insufficient_information`,
39/54 реальных exact, 0/1 OOD, 213+103 своевременных
HTTP-ответов, ноль изменившихся ответов. Исторический p95: frozen 4,853 с,
organizer 4,964 с; 94/213 frozen дольше 3 с. Private receipt:
`/Users/skif/ml-data/brutforce/cpu-evidence-20260926/ort6-selfcheck-private-v2.json`.
Это проверка схемы и воспроизведение старой оценки, не новое измерение TEST.

Свежий парный контроль runtime-исполнителя (14:23 МСК):
`/Users/skif/ml-data/brutforce/cpu-evidence-20260926/ort6-paired-v2.jsonl`
(SHA-256 `b11f721ecc8d3c11465740767ec51b2e0fd21aaaef18419438c57d272eeec0eb`)
и `ort6-paired-organizer.jsonl`
(SHA-256 `bcb1b701d76d1c7424b08cd4df1f9816a6b985b6625080863b386436b95ae21d`).
Все 316 запросов завершены вовремя; относительно архивного ORT6 нет ни одного
изменения action, slug или полного ранга — 0/213 и 0/100 уникальных organizer.
Качество сохраняет 110/141, 56/62 и 39/54; свежий p50/p95/max frozen:
2,484/4,348/4,840 с, organizer: 3,799/4,484/4,796 с. Сравнение с историческим
замером показывает вариативность времени; для кандидата используем именно
свежие парные пределы p95 ≤5,348 с frozen и ≤5,484 с organizer.
Ни один из 316 ответов свежего контроля не превысил и product budget 8,5 с.
Private receipt: `/Users/skif/ml-data/brutforce/cpu-evidence-20260926/ort6-fresh-vs-historical-private-v3.json`.

## Диагностика качества исходного ORT6 (до кандидата)

На 54 уникальных `exact` organizer из исправленной sealed-аннотации, с
overlaid одним проверенным OOD, парный ORT6 даёт: correct Top-1 **39**;
wrong Top-1, но gold в Top-5 **11**; gold на позициях 6–20 **0**;
gold отсутствует в Top-20 **4**. Итого gold в Top-20 — **50/54**.
Для перестановки только исходного Top-20 это *oracle-потолок* 50/54,
если не испортить 39 правильных ответов и суметь поднять все 11;
это не предсказанный выигрыш реализации. Именно проверяемый rerank —
крупнейший доступный механизм, а остальные четыре случая требуют
target/gate или расширения candidate recall после отдельного разбора.

На этих же 100 уникальных кадрах исходное действие: 52 `match` и 2
`no_match` среди 54 exact (оба `no_match` ложные); на единственном
подтверждённом fixed-catalog OOD — `match` (ошибка). Остальные 42
`catalog_unresolved` и 3 `ambiguous` тоже вернули `match`, но не являются
проверенными отрицательными метками. Отдельная frozen v2 проверка даёт
19/22 `no_match` и 0/10 `insufficient_information` по своим verified
поднаборам; эти поднаборы нельзя смешивать с organizer denominator.

В существующем визуально проверенном аудите
`vision-retrieval-20260925/annotation/real54-error-analysis.md` описаны
ошибка hard non-wine gate на одном из отсутствующих в Top-20 кадров и
выбор соседней бутылки в другом. Аудит
`absence-audit/parent-exact-errors-v1.json` дополнительно документирует
две ложные gate-отсечки; обе сохраняют в свежем ORT6 действие `no_match`
и отсутствие gold в Top-20. Причину четвёртого отсутствия не назначаем:
аудиты относятся к сохранённым прежним композициям, а не являются
разметкой внутренней причины каждого ответа ORT6. Диагностика построена
на повторно используемом development-наборе, не holdout.

## Первый кандидат `4bcc925`: sealed frozen 213

Sealed candidate raw:
`/Users/skif/ml-data/brutforce/cpu-evidence-20260926/candidate-4bcc925-p1280-v2.jsonl`,
SHA-256 `7dc3af42384e8f94bfe7147cdaf03f321f0dd55f8b9efc6495eeeaf0cc8de4b7`.
Все 213 ID и входных SHA прошли проверку, HTTP 200 — 213/213; единый
`model_version`/`serving_profile`: `rtdetr-so400m-whole-only-v1-onnx640-evidence-v1` /
`so400m-onnx640-evidence-v1`. По сравнению со свежим ORT6 нет ни одной
перестановки или смены action/slug: service 110/141, retrieval Top-1 56/62,
`no_match` 19/22 и `insufficient_information` 0/10 сохранились. Это
измеренный **no-gain** frozen-части.

OCR использован в 33/213 запросах (service 14, retrieval 19). Для них
`evidence.state`: `producer_not_observed` 10, `grape_not_observed` 17,
`family_not_observed` 6; `visual_winner_supported` 0 и `ambiguous` 0.
У остальных 180: `not_eligible` 133, `no_selected_target` 29,
`target_overlaps_other_bottle` 18. Из 33 OCR-вызовов 17 дали по одному
`observation` (family 14, producer 3, grape 0), 16 — ни одного;
`candidate_evidence` пуст во всех 33, `before == after` во всех 213.
Наблюдений, разрешающих выбор между карточками, по этому диагностическому
контракту **0**. Не выводим из этого недоказанную единственную причину.

До административной паузы frozen p50/p95/max: ORT6
2 484,48 / 4 348,25 / 4 840,25 мс; кандидат
3 011,44 / 4 837,75 / 5 993,06 мс. Разница p95 +489,50 мс;
запросов >3 с: 88→109, >8,5 с и >10 с: 0. Frozen время допустимо
рассматривать отдельно с учётом runtime receipt. После 48 законченных
organizer-запросов runner приостановлен 26.09.2026 в 12:04:11.556 UTC;
следующая строка 049 затронута паузой и остаётся в исходном наборе без
ретрая (HTTP 200, wall 177 369,12 мс). После 84 законченных organizer-запросов
вторая пауза началась в 12:09:29.676 UTC; затронута строка 085.
Это административные интервалы, не доказанная модельная задержка.
Organizer latency и общий timing gate по такому прогону не
подтверждаются, независимо от численного p95. Organizer quality и полный
quality verdict ожидают sealed 103/103 и итоговый receipt.

### H2 `4a36086`: только offline replay имеющихся OCR

На доверенном Mac выполнен неизменённый `field_matcher.py` из source
`4a36086b736933fb70b40ed96f8d02de644dad3f` с зафиксированными
`matcher.py`/`ranking.py` от `4bcc925`, pinned 2 103 catalog cards
(SHA-256 `5ffb93714c611efbe541028f44dff84dfc0646451c364caee979869d1548be9a`)
и сохранёнными буквальными OCR `texts`/`scores` **только 33** frozen-запросов
первого кандидата. Источники, входные SHA, private case-level сравнение и
ограничения: `/Users/skif/ml-data/brutforce/cpu-evidence-20260926/h2-4a36086-frozen33-private-replay.json`
(SHA-256 `685bc1a27533b2bd83fe676ea1be2e70f41e84863ee9a92c482581d010beea4b`).

H2 eligible 33/33; `insufficient_field_evidence` 33/33, наблюдение поля grape
1, producer 0, line 0; неоднозначное сопоставление line 14, producer 3.
Среди 660 оценённых кандидатных позиций: supported 0, unknown 656,
contradicts 4. Перестановок ранга 0; на **только этих 33** размеченных
входах правильность 28→28, исправлений 0, ухудшений 0. Gold-blind разбор:
фраза grape хотя бы одного из Top-20 встречается в нормализованных OCR
literal при любом confidence в 1/33 кадре; при пороге ≥0,75 тоже в 1/33.
На этих сохранённых входах снижение порога confidence само по себе не
объясняет отсутствие grape-свидетельств; это не доказательство точности OCR.
Для остальных 180 frozen нет сохранённого OCR: counterfactual **не измерен**.
Replay не является полным результатом H2 по HTTP, качеству или latency.

### Нормализация grape `cc6eb78`: offline ablation тех же 33

Проверен точный diff от H2: `GrapeNormalizedFieldMatcher` применяет
каталожно подтверждённые соответствия к `cards.title` **до**
`card_identity` и к OCR; полная grape-фраза может проходить через две
соседние строки с минимальным confidence. Порог ≥0,75 не менялся.
По pinned публичным cards активны только `Cabernet Sauvignon` →
`Каберне Совиньон` (поддержка 19, конфликтов 0) и `Chardonnay` →
`Шардоне` (22/0); остальные четыре конфликтные пары нейтральны.
Источник `cc6eb7833235952f271f58a05c7a787c5b33b41d`, те же sealed
raw 33, pinned cards и trusted gold. Source/input SHA и private детали — в
`/Users/skif/ml-data/brutforce/cpu-evidence-20260926/grape-normalization-cc6eb78-frozen33-private-replay-v2.json`
(SHA-256 `1791da499d914aeae41de7e34be6e173286301f0dc0d093af539142f1b225247`).

Подтверждено независимым replay: наблюдаемый grape **1→8/33 запросов**
относительно H2; gold-blind совпадение grape-фразы Top-20 с OCR literal
после нормализации при любом confidence 9/33, при ≥0,75 — 8/33.
Наблюдаемый line 3, producer 0; неоднозначный line 14, producer 3.
`insufficient_field_evidence` 31, `visual_winner_not_contradicted` 2;
поддержанных identity 0/660 позиций, rank flips 0, качество на этих
33 остаётся 28→28, исправлений/ухудшений 0/0. Текстовое совпадение
улучшилось, но downstream-решение не изменилось. У оставшихся 180 нет
сохранённого OCR; это не результат полной H2-проверки, HTTP-замер или
доказательство выигрыша ML/latency.

## Парная оценка кандидата

Вход: исходные 316 публичных изображений с проверкой SHA, каждый полный HTTP-ответ
один раз без замены поздним ответом. Runtime-исполнитель выделяет по расписанию
изолированные `8127/8129` и готовит свежий контроль ORT6 на том же Sigma CPU;
`8125` не нагружаем параллельно. Сохраняются `case_id`, `track`, `query_sha256`,
`manifest_sha256`, HTTP status, wall `elapsed_ms`, `action`, `slug`, Top-20,
версии, стадийные времена и ошибки; gold не передаётся на inference.

Scorer: [tools/cpu-evidence-eval/score.py](../../tools/cpu-evidence-eval/score.py).
Первый кодовый кандидат разработчика: commit `c80f00c`; обновлённый bridge
source `4bcc925` (сообщение исполнителя ML-083) пересылает запрос один раз
в ORT6 `8125` с opt-in loopback target metadata и выборочно вызывает OCR
worker `8129`. Сохраняет исходный matcher и пул кандидатов, передаёт
`ranked_slugs`, `image_sha256`, версии, track и diagnostics evidence; ошибки OCR
явные, догадок по тексту нет. Бюджет wrapper — 8,5 с минус резерв 350 мс.
Координатор одобрил только диагностический TEST diff `4bcc925`; полный
HTTP-прогон кандидата остановился на organizer 84/103, frozen часть выше измерена. У контроля прямой TEST
`8125` без `CPUQuota`, шесть потоков и `MemoryMax=7 GiB`; у кандидата есть
дополнительные wrapper/OCR-этапы. Квоты и конкуренцию ресурсов учитываем при
интерпретации измерений; флаг `paired` scorer не заменяет review runtime receipt.
Кандидат проходит gate только при **положительном net exact** с исправлениями
минимум двух разных scene groups, service ≥110/141 и retrieval Top-1 ≥56/62
на одинаковой frozen v2, без новых ошибок известных отрицательных сцен,
без новых ответов за 10 с/timeout и при p95 не хуже парного ORT6 больше чем
на 1 с (frozen и organizer отдельно). Каждый изменённый ответ и правильность
лежат в приватном receipt; здесь будут указаны все flips без private gold.
Время считаем по всем запросам, рядом условные перцентили только timely HTTP200;
дополнительно показываем число >8,5 с — бюджет приложения (downstream timeout).
Цель 3 с оценивается отдельно. Organizer54 — повторно используемая development
диагностика, Roman16 пока не допущен, снимок KAFFA не является holdout.

Проверка происхождения KAFFA: SHA-256 двух присланных JPEG-скриншотов
`2539162e7cb8354080a59efda146642894e1f8359f4d9263ce50463808fb67fe`
и `299fcbcd856f9c6c1e673cc9b6e7117b4d0f4ae00e6971deee5bceb2cd706985`
не совпадают ни с одним SHA входа organizer103. Это сравнение байтов
скриншотов, а не доказательство отсутствия снятого на них кадра в наборе;
визуальное соответствие с исходными кадрами не установлено. Метку по
выходу модели не назначаем.

## Закрытие ML-083 по дедлайну, 17:22 МСК

- Чистые 213 frozen сохранены и проверены: SHA-256 `7dc3af42384e8f94bfe7147cdaf03f321f0dd55f8b9efc6495eeeaf0cc8de4b7`, HTTP 200 — 213/213, изменений рангов/действия 0; качество service 110/141, retrieval 56/62, p95 4,838 с против ORT6 4,348 с. Исправлений нет.
- Незавершённый organizer raw экспортирован **отдельно** в `/Users/skif/ml-data/brutforce/cpu-evidence-20260926/candidate-4bcc925-p1280-organizer-partial84.jsonl`: SHA-256 на Sigma и Mac `1a61d8b9e582cc8f126ecbeeb0f344e90f7d49828d49820b94aecb76bf6c55c5`. Полных строк 84/103, уникальных ID 84, HTTP 200 — 84; одна wall latency >10 с относится к административной паузе запроса 049 (177,369 с), не доказанная модельная задержка. Вторая пауза застала запрос 085 без строки; его не повторяли и не подменяли. Runner `Result=timeout` из-за собственной отсечки после длительного согласованного ожидания окна demo. Частичные 84 нельзя оценивать как полный organizer54/gate, их нельзя смешивать с чистым p95.
- Gate **не пройден/не установлен**: нет продемонстрированного прироста exact и полного organizer-прогона; финальный CPU-rerank в Maks/TEST не выпускался. Действующий `8125` — ORT6 с opt-in диагностическим кодом без evidence URL; обычные ответы на пяти публичных входах были эквивалентны контрольным, прежний release сохранён для отката. App upload/search smoke на свободном слоте: HTTP 201→200, пять кандидатов; в период benchmark встречались 503, связь с конкретным пользовательским запросом не установлена.
- Временные wrapper8127 и OCR8129 остановлены (`inactive/dead`); TEST8125 `ready`, `busy=false`; RunPod pod/volumes — 0/0, аренда $0. Это итог первой CPU-ветки. Следующая отдельная проверка предложений Pro: построить карточку наблюдений целевой фотографии, затем независимые R1 (reader+matcher), R2 (VL reranker того же Top20), P1 (отложенный gate/выбор цели). Reused organizer54 — development, не holdout; исходный KAFFA upload не установлен.
