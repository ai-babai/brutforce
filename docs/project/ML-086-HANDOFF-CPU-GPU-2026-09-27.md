# ML-086 · передача CPU/GPU для старшей сессии · 27.09.2026

Статус: документальный handoff после завершения задачи #86; **release NO-GO**.
Канон измерений — [ML-086-RESULTS](ML-086-RESULTS-2026-09-26.md),
ветка `codex/ml086-eval`, baseline commit `0c2cbb7bab070995a2d3cd23e68953446562baae`.

## 1. Executive summary · читать сначала

- **ML-086 закрыта:** новых экспериментов в этой передаче **0**; RunPod, SSH,
  inference, загрузок, live TEST и изменения gold не было. Verdict остаётся **NO-GO**.
- **CPU anchor — ORT6 FP32, 6 потоков:** sealed full HTTP 316/316, frozen
  service 110/141, retrieval Top1 56/62, organizer exact 39/54. Это контроль,
  не доказательство качества на независимом release-наборе.
- **GPU lead — R1 v6 Qwen:** fixed ORT6 Top20, full-frame loopback HTTP
  316/316 на Pod B, 115/141, 59/62, 43/54; organizer fixed 4/broken 0
  в 3 размеченных группах. Изолированный harness принимает лишь sealed
  manifest, не произвольное фото; перенос на CPU/Sigma и cold E2E не доказан.
- R2 даёт 48/54 на том же ORT6 Top20, но имеет broken и 156/316 локальных
  запросов >10 с. Roman adapter20 даёт 50/54 **на другом B-пуле** и не имеет
  full HTTP316. P1 даёт 42→44/54 только против собственного GPU-контроля.
- Здесь две **очереди гипотез** и контракт следующего измерения, не разрешение
  на compute, TEST/demo или сдачу; development gate не равен release holdout.

## 2. Наборы, фото и знаменатели

| Единица | Состав и граница |
|---|---|
| 316 request ID | 213 frozen v2 + 103 organizer; это запросы, не независимые сцены. |
| Frozen 213 | 141 graded service + 62 graded retrieval + **10 ungraded service**. Всего по происхождению 42 real + 120 augmentation + 51 AI. |
| Graded service 141 | 32 real + 70 augmentation + 39 AI; по действию 109 match + 22 no_match + **10 graded insufficient_information**. Эти 10 не равны 10 ungraded service. |
| Retrieval 62 | 50 augmentation + 12 AI; независимых реальных retrieval-фото нет. Вход — проверенный crop, не полный сервисный кадр. |
| Organizer 103 | 100 unique image SHA: 54 exact, 42 unresolved, 3 ambiguous, 1 подтверждённый OOD. Exact: 37 SKU, 42 размеченные группы сцен; latency — все 103 HTTP. |
| Совокупный SHA | Frozen: 212 уникальных SHA на 213 ID; пересечение с organizer: 12 SHA. `212 + 100 − 12 = 300` уникальных image SHA, **не** 300 независимых capture/сцен. |

Organizer exact54 многократно использован как development; 42/3 не размечены
exact, один OOD не калибрует отказы. Независимые frozen-группы — **missing**.
Подборка Roman16 — только staging (`expected_slug/central_target=null`,
`scored=false`, история train/validation сохранена), не новый gold/holdout:
[аудит фото](ROMAN-PHOTO-SCREEN-2026-09-25.md).
Приватный trace **9×316** — маршруты по тем же ID, не новые тесты;
`observed`/`missing` не доказывают причинность ошибки. Знаменатели:
[ночной отчёт, строки 68–83](NIGHT-EXPERIMENT-RESULTS-2026-09-25.md),
[канон, строки 38–55](ML-086-RESULTS-2026-09-26.md).

## 3. Матрица измеренного · разные пулы и scope

Значения ниже: frozen **service action+slug /141**, retrieval **Top1 /62**,
organizer **exact Top1 /54 unique SHA**. Retrieval Top5/20, organizer Top5/20
и действия отказа — отдельные метрики. `fixed/broken` указан только к явному
контролю; группы — размеченные organizer development-группы, не release-сцены.

| Маршрут / контроль | Service · retrieval · exact | Парные сдвиги organizer; pool и охват | Время / итог |
|---|---|---|---|
| **ORT6 CPU6**, anchor | **110 · 56 · 39**; retrieval Top5/20 62/62, exact Top5/20 50/54 | Сам себе контроль; 19/22 no_match, 0/10 insufficient, OOD 0/1. Из 15 exact ошибок 11 в итоговом Top20, 4 вне его; oracle перестановки 50/54. Исторический pre-pool/selected box missing. | Sigma sealed full HTTP p95 frozen **4,348 с** /213, organizer **4,484 с** /103; >8,5 и >10 с 0/316; cold E2E missing. Исторический TEST, не новый live check. |
| **R1 GPU v6** ↔ ORT6 | **115 · 59 · 43**; retrieval Top5/20 62/62, exact Top5/20 50/54 | Тот же ordered ORT6 Top20; fresh box/JPEG сверены в v6, historical ORT6 box missing. Service fixed 5/broken 0, retrieval 3/0, organizer **4/0 в 3 группах**; OOD 0/1. 285 crop +31 подтверждённый fallback. | Pod B EPYC7443 quota 10,2 cores + RTX PRO4500, warmed sequential full HTTP316, offline↔HTTP predictions 316/316; p95 **4,388/4,872 с**, >8,5/>10 0/316; client deadline 30 с, cold E2E missing. Harness sealed-only; NO-GO. |
| **R1 Paddle CPU v6** ↔ ORT6 | **110 · 58 · 40**; exact Top20 50/54 | Тот же ORT6 pool/JPEG; service fixed **1/broken 1**, retrieval 2/0, organizer **1/0 в 1 группе**; OOD 0/1. | Pod A CPU2 OCR offline cached; full CPU HTTP **missing**. Stage p95 не HTTP; NO-GO. |
| **R2 Qwen VL** ↔ ORT6 | **117 · 62 · 48**; exact Top20 50/54 | Тот же ORT6 Top20; service fixed **9/broken 2**, retrieval 6/0, organizer **11/2**, 8 выигравших/1 проигравшая группа. R1↔R2 crop bytes отличаются 285/285: не чистый эффект reranker. | Pod B local in-process, без HTTP upload: p95 **14,253/18,939 с**, >10 с **156/316 local**, не HTTP timeout; startup→config 109 с (включая init/SHA), process wall 3 263 с; full HTTP/cold E2E missing. NO-GO. |
| **P1 upstream** ↔ свой same-model GPU | **114 · 57 · 42→44**; P1 exact Top5/20 51/53, контрольные ранги missing | Frozen без изменений, organizer **2/0 в 2 группах**; post-gate recall 53/54, pre-gate slug pool отсутствует по архитектуре; target truth IoU missing. Другой upstream/model, не складывать с R1. | Pod A warmed full HTTP316, p95 **3,512/4,722 с**, >8,5/>10 0/316; cold load отдельно 85,077 с, cold E2E missing. NO-GO. |
| **Roman adapter20** ↔ B | **119 · 61 · 50**; B **114 · 57 · 44**; B exact Top20 53/54 | B↔adapter20 service fixed 5/broken 0, retrieval 4/0, organizer **6/0 в 6 группах**. adapter5↔20 organizer 5/1; разная eligibility (237 judge, 51 missing references, 28 no-candidates). B Top20 совпадает с ORT6 лишь в 28/213 frozen и 0/103 organizer: **не** парное сравнение с ORT6. | Pod D cached judge stage, full HTTP316/cold missing; fresh GPU HTTP smoke 2/3 HTTP200 +1 client timeout. CPU fp32 ×2 model-only **21,990/23,248 с**, digit drift 1/2, не p95/HTTP и не GPU-equivalence. CPU route NO-GO; release NO-GO. |

Детали исходных SHA/raw и аппаратных условий — [канон §§ R1/R2/P1/Roman,
«Задержка по scope»](ML-086-RESULTS-2026-09-26.md). ORT6 Sigma,
Pod A/B/D и cached/local/full HTTP **не** одинаковый hardware/timing scope;
ночной ORT6 p95 4,85/4,96 с — другой прогон, не paired baseline 4,348/4,484.
Изменённый ранг не гарантирует правильное service action.
По decision trace причинная стадия ошибки **unknown**: отсутствие slug в
итоговом Top20 или незаписанного upstream pool само по себе не доказывает
неверную физическую цель, wine gate либо OCR.

**Исторический gate ML-083/086**, не новый SLA-план: прирост exact в ≥2
размеченных группах, frozen service/retrieval Top1 не ниже ORT6, без новых
известных отрицательных ошибок и timeout >10 с, full HTTP paired p95 не более
ORT6 +1 с (**≤5,348/5,484 с** при сопоставимой паре). Приложение исторически
имело vision budget **8,5 с**, checkout [eval boundary](../../contracts/eval-predict.md)
задаёт context **9 с** (здесь Recognizer nil), конкурсный клиент — **10 с**;
цель ТЗ **3 с** отдельно. Это разные границы; актуальную live TEST/runtime
версию и forced deadline этой сводкой не проверяли. R1/P1 post-hoc нули
превышений не доказывают forced 8,5-с end-to-end SLA.

## 4. CPU · ранжированная очередь опытов (предложения)

Все пункты — **по одному фактору** с явно названным контролем; ORT6 — anchor. Сначала
малый gold-blind discovery slice для механизма и ошибок, затем, только при
основании, полный **316 regression**. Ни slice, ни regression не holdout.
Скоринг private labels — только доверенным scorer после freeze.

1. **Выбор физической цели.** Evidence: [PLAN, ML-03](PLAN.md) — удаление
   составных боксов ухудшило 42→40/54; ORT6 historical selected box missing.
   Фактор: ключ выбора среди уже допущенных боксов; detector/gate/encoder,
   алгоритм пула и index фиксированы, **фактический pool может смениться с crop**
   и записывается. Минимум: fresh gold-blind box trace и paired replay ключа
   против ORT6; контроль тот же input/model, отдельно CPU HTTP316 при сигнале.
   Learn: меняется ли цель, а не вывод о root cause из Top20 loss. Метрики:
   changed box/pool, проверенная target IoU только при принятой bbox-схеме,
   service/retrieval/exact fixed/broken и группы, negatives, full HTTP p95/
   deadlines. Stop: нет релевантных смен цели, новая frozen/negative регрессия
   или нет обоснования двух групп; старую цель не реконструировать из золота.
2. **Ограниченный текстовый candidate expansion.** Evidence: 4/54 exact вне
   ORT6 Top20; постоянный CPU OCR проигрывал по timeout
   [ночному контролю](NIGHT-EXPERIMENT-RESULTS-2026-09-25.md).
   Фактор: добавить OCR-generated кандидатов по выбранной цели **только в
   диагностический пул**, не менять gate/answer и не возвращать quarantine
   reference. Минимум: gold-blind eligibility + одинаковые target crops;
   контроль ORT6 Top20 50/54, trusted scorer оценивает recall нового пула.
   Learn: расширяется ли достижимый ответ, не «улучшается ли Top1».
   Метрики: pool recall/ложные кандидаты, неизменность ответов, OCR failures,
   HTTP p95/>8,5/>10 при переходе к сервису. Stop: нет новых доступных
   эталонов у eligible, изменён ответ без отдельного rerank-опыта или timeout.
3. **Rank внутри fixed Top20: абляция grape-only promotion.** Evidence:
   11/15 ORT6 exact ошибок имеют правильный Top20; Paddle v6 дал лишь 1
   organizer группу и 1 broken service. В R1 `match.py:95–145` **уже**
   считаются `producer_hits/title_hits`: без producer у Top1 нет rerank,
   меняются только позиции его producer family, сортировка — contradiction,
   затем title, затем grape. «Добавить title+producer» не новый фактор.
   Фактор: при неизменном Paddle v6 OCR/target/JPEG/ORT6 Top20 запретить
   **только grape-positive повышение без title hit** внутри той же семьи;
   прочие сравнения оставить как в v6. Минимум: заранее закрепить правило
   без gold, paired replay против **неизменного Paddle v6 и ORT6**; только
   после сигнала CPU full HTTP. Learn: были ли grape-only перестановки
   причиной регрессий или полезных исправлений. Метрики: triggered moves,
   141/62/54, Top1/5/20, fixed/broken/группы, negatives, OCR/HTTP ошибки.
   Stop: фактор не срабатывает, новый broken, <2 выигравших групп или
   нарушение времени; потолок fixed pool — 50/54.
4. **Недостаточность как отдельное действие.** Evidence: ORT6 0/10 graded
   insufficient и 0/1 OOD, при 19/22 no_match; это не проблема сортировки SKU.
   Фактор: только заранее определённый gold-blind confidence/abstain rule
   без смены рангов. Минимум: публичный signal и отдельные новые negative
   сцены для разработки/калибровки порога, иначе остановиться; затем paired
   regression. Запечатанный release holdout — отдельно, порог на нём не подбирать.
   Learn: true reject против false reject, а не калибровка по одному OOD.
   Метрики: все классы действий, false rejects positive, Top1, p95/errors;
   stop при произвольном пороге, новом ложном отказе или ухудшении gate.

Не возвращать как «ускорение»: несогласованный query INT8/FP32 index дал
65/141 service; постоянный второй CPU crop — 98/141; постоянный Paddle OCR
имел timeout; Roman CPU ×2 превышал 10 с уже на model-only. Это отрицательные
контроли **конкретных** реализаций, не запрет согласованного нового метода.
Условный выбор между **неизменными** ORT6 и Paddle v6 может сохранить
единственный organizer fixed, убрать frozen broken и сократить OCR-время,
но не создать >1 organizer fixed (у Paddle v6 fixed 1/broken 0). Это
оптимизация **после** нового quality-кандидата, не самостоятельная гипотеза
на ≥2 группы.

## 5. GPU · отдельная ранжированная очередь (предложения)

Развилка для старшей сессии: **интеграционный R1 arbitrary-photo baseline**
обязателен для demo; quality research ниже — только после выбора фактора.
Нумерация гипотез не делает P1 обязательным первым опытом будущей фазы.

1. **Upstream P1: gate/target provenance.** Evidence: P1 +2/54 против
   same-model 42/54, post-gate Top20 53/54, но truth IoU missing. Фактор:
   P1 upstream on/off при фиксированном downstream/model и paired фото;
   **изменения target/pool допустимы как измеряемый эффект фактора**.
   Минимум: gold-blind запись target, gate decision, post-gate pool;
   у rejected до retrieval **нет pre-gate slug pool**. Условный forced
   continuation — лишь отдельная диагностика, не production path/его recall.
   Learn: покрытие/выбор цели против изменения ответа; IoU лишь при принятой
   bbox-разметке. Метрики: 54 exact recall, 141/62, fixed/broken/группы,
   negatives, HTTP deadlines. Stop: provenance/схема отсутствуют либо новый
   negative/служебный broken; не приписывать +2 одному gate без абляции.
2. **P1 в R1 — отдельный interaction test.** Evidence: R1 39→43/54,
   P1 на *другом* same-model GPU 42→44/54, общего raw нет. Фактор: только
   upstream P1 on/off при pinned R1 reader/matcher/JPEG и одной модели;
   paired input и R1-only контроль на одной машине. Target/pool могут
   закономерно измениться, это логируется, не скрывается как «тот же pool».
   Минимум: сначала trace upstream, затем полный HTTP316 только при готовом
   контроле. Learn: даёт ли комбинация реальный эффект без сложения +4/+2.
   Метрики: box/crop/pool, 141/62/54 fixed/broken/группы, negatives,
   full HTTP p95/timeout/cold. Stop: нет воспроизводимого контроля или broken.
3. **R2 crop-view ablation.** Evidence: R2↔R1 на одних box/Top20 имеет
   organizer fixed 7/broken 2, но **285/285** crop bytes различаются;
   R2 local >10 с 156/316. Фактор: только JPEG768 ↔ original PNG при
   одном pinned R2/batch1/prompt/Top20 и железе. Минимум: paired sealed
   predictions, отдельно bounded serving timing, не сумма стадий.
   Learn: доля view effect и достижимость 10 с, не «эффект R2 против R1».
   Метрики: ranks/Top1/5/20, fixed/broken, negatives, crop SHA, local и
   затем HTTP p95/>8,5/>10. Stop: regression или недостижим deadline.
4. **Roman patch parity перед serving.** Evidence: B→adapter20 44→50/54,
   но это B-пул; Conv3d→F.linear bounded сверка не доказывает серию, fresh
   HTTP smoke 1/3 timeout. Фактор сначала **только patch on/off** при том
   же B Top20/adapter20/eligibility. Минимум: gold-blind logits/digits/ranks
   на закреплённом срезе; контроль original runtime, затем отдельный full
   HTTP с настоящим client deadline. Learn: parity и стоимость; **смена
   B↔ORT6 pool — другой опыт**. Метрики: drift, rank/digit parity, errors,
   VRAM/stage и затем full HTTP. Stop: rank/digit drift, OOM или deadline;
   cached 237 judge не считать полным сервисом.

**Отдельная интеграционная задача, не quality gain:** R1 `http_harness.py`
требует `X-Case-ID`, сверяет SHA с 316 manifest и заранее известные box/
Top20/JPEG/fallback. Для произвольного фото нужен живой путь ORT6→target→
reader→matcher и честный no-target/error, без lookup по sealed ID. Проверить
новые допустимые публичные/синтетические фото, форматы, отмену, concurrency
и действительный slug по [контракту](../../contracts/eval-predict.md),
затем независимый sealed scoring; это ещё не TEST и не обещание CPU-portable
runtime. HTTP parity316/316 на известных SHA произвольное фото не доказывает.

## 6. Контракт следующего опыта и правила остановки

1. **До вычисления:** владелец фиксирует source commit и file SHA (локальный
   uncommitted source так и обозначить), config/input/model revisions и SHA,
   catalog/index, crop transform, target policy, ordered pool и fallback.
   Для rerank-only box/crop bytes/Top20/eligibility идентичны; для upstream
   on/off смены target/pool записываются как эффект. Gold на inference-хост
   не передавать; новый holdout после freeze не использовать для настройки.
2. **Ресурсы:** задать аппаратный профиль, quota/threads/GPU, concurrency,
   budget, owner, stop time и контроль той же машины/маршрута. Разделять
   local stage, local in-process, full client HTTP и реальный TEST ingress;
   cold load/cold first end-to-end, warm и wall измерять отдельно.
3. **Каждый ID:** полный вход и raw строка, status HTTP, action/slug/ranks,
   pool/target/crop provenance, fallback/not_run, error/timeout с временем
   клиента; server-complete после client timeout не успешный ответ. Отдельно
   213/103 и graded 141/62/54, negatives 22/10/1, дубли SHA/группы.
4. **Метрики:** Top1/5/20, MRR, fixed/broken/оба верны/оба неверны к названному
   контролю, изменившиеся группы и SKU, coverage; p50/p95/max на одной
   определённой latency scope плюс >3/>8,5/>10 и ошибки на **всех** ID.
   Для **all-client attempt-duration** включать измеренный elapsed timeout
   в n попыток (при полном 213/103/316 позиции nearest-rank p95:
   203/98/301); это не completion latency: timeout цензурирует завершение.
   **Success-only latency** считать отдельно, с n только успешных ответов:
   `x[ceil(0,95n)]`; нельзя исключить timeout и сохранить знаменатель 316.
   Пороговые доли/errors — от всех запросов; не смешивать с linear p95.
5. **Малая discovery-проверка** решает, измерим ли фактор; не является gate.
   Full316 — регрессия на знакомых данных, не новый holdout. Публиковать
   качество только агрегатами; private ответы/trace остаются у trusted scorer.
   Не улучшать порог по тем же ответам и не объявлять development success GO.

## 7. Навигация и provenance для следующего исполнителя

- Главные документы этого checkout: [ML-086 измерения](ML-086-RESULTS-2026-09-26.md),
  [ночные отрицательные контроли](NIGHT-EXPERIMENT-RESULTS-2026-09-25.md),
  [PLAN и исторический gate](PLAN.md), [правила данных](../agent-guide/DATA-RULES.md),
  [Roman handoff](ROMAN-HANDOFF-2026-09-25.md). Этот draft не меняет их историю.
- ORT6 исходники в `codex/ml086-eval` @ `0c2cbb7…`:
  [night_server.py](../../tools/night-cpu/night_server.py),
  [onnx_so_pipeline.py](../../tools/night-cpu/onnx_so_pipeline.py),
  [fast_owl_pipeline.py](../../tools/night-cpu/fast_owl_pipeline.py),
  [run_http.py](../../tools/night-cpu/run_http.py),
  [whole_encoder_server.py](../../tools/vision-retrieval/whole_encoder_server.py),
  [model.py](../../tools/vision-retrieval/model.py),
  [fuse.py](../../tools/vision-retrieval/fuse.py),
  [ranking.py](../../tools/vision-retrieval/ranking.py).
- R1 source: `/Users/skif/develop/brutforce-ml086-r1-target-card/`,
  `codex/ml086-r1-target-card` @ `fb59b852b49f94d6d618b2cee7578fae04fe0885`;
  `tools/ml086-r1/{README.md,prepare.py,reader_view.py,reader_inputs.py,match.py,http_harness.py,http_client.py}`.
  Source/config/raw full SHA — [канон §§ R1](ML-086-RESULTS-2026-09-26.md).
- P1 source: `/Users/skif/develop/brutforce-ml086-p1-gate/`, чистая
  `codex/ml086-p1-gate` @ `c32839f55752887c3f1c20762d2a55edb39f0aee`;
  `tools/vision-retrieval/p1_gate_server.py` SHA-256
  `e7a2dd97514d11cd9d4bc4484159a25857d99698435384b1cebf5e9299583fd9`
  (локально сверен с [каноном § P1](ML-086-RESULTS-2026-09-26.md)).
- R2 source: `/Users/skif/develop/brutforce-ml086-r2-vl/tools/night-qwen-http/r2_ort6.py`,
  **local untracked**, SHA-256
  `8dcc6f51e2b7b1ad3029a9684944a85f37f83387b5ddb34f0b118cb637149114`;
  не считать commit текущего worktree публикацией этого файла.
- Roman source: `/Users/skif/develop/brutforce-ml086-roman/tools/night-roman/run.py`,
  **local modified** на `codex/ml086-roman` (worktree tip `cb6679a4058bf9c407972fefed2522a543f7bb69`),
  patched file SHA-256
  `832fad2f9ffda834530119d5b7bac5362587ef828082824ddbafd78ab9963893`;
  `export_ml086.py` там untracked; это не заявление о push.
- Mac roots **вне Git**, не копировать raw/private в handoff:
  `/Users/skif/ml-data/brutforce/{night-20260925/,ml086-eval/,ml086-r1-20260926-reader-view-full/,ml086-r2-vl/,ml086-p1-gate/,ml086-roman-20260926/}`;
  аппаратный receipt `/Users/skif/ml-data/brutforce/ml086-hardware-receipt-20260926.json`;
  R1 `per-run-timing-provenance.receipt.json`, P1 `RUNTIME-RECEIPT.md`,
  Roman `latency-hardware-checkpoint.md`, scorer receipts внутри `ml086-eval/`.
  Runtime journal: `infra-os/runs/2026-09-26-lct-ml086-runtime.md`
  (другой репозиторий; серверные пути не выводить из Mac-путей).

## 8. Решения старшей сессии · до 11:00 МСК 27.09

- Старшая сессия заранее представит **два плана**, CPU и GPU, с первым
  фактором, контролем и stop. **11:00 МСК — срок выполнения первой будущей
  фазы после отдельного старта**, не срок подготовки планов и не обещание
  успеть все гипотезы или выпуск; этот документ фазу не запускает.
- Новое разрешение пользователя — **потолок будущей фазы**: до 2 pod на
  направление, до 4 одновременно всего. Здесь pod **0**; не резервировать
  по самому факту потолка. Новую общую сумму USD этой сводкой не фиксировали;
  старые лимиты $1,50/ч, $6/ч и дедлайн 18/22 ч из
  [правил итераций](../agent-guide/OPERATING-RULES.md) исторические,
  автоматически не продлеваются.
- Перед отдельным стартом нужны owner pod/lifecycle, тариф, storage,
  новый бюджет и stop time, immutable protocol и независимый scorer.
  Изменения demo/TEST/доступов — отдельное поручение и live-проверка.
- Независимый real holdout **missing**. Даже если следующая development-
  гипотеза улучшит текущие 54 exact, это не доказательство выпуска.
