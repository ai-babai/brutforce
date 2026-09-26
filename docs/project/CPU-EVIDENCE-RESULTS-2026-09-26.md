# ML-083 · CPU evidence: независимая оценка

Статус: подготовлен контроль и доверенный scorer; измерения кандидата ожидаются.
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
Координатор одобрил TEST diagnostic diff `4bcc925`; runtime готовит полный
HTTP-прогон кандидата, результатов качества пока нет. У контроля прямой TEST
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

До получения полного набора ответов кандидата и парного замера gate **не установлен**.
