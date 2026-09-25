# Air / v3.4: аудит BDD перед реализацией

Дата: 25.09.2026. Основание: новое согласование Макса в текущей задаче — Air/v3.4,
новые BDD/тесты и замена устаревших проверок разрешены. Это аудит, не реализация.
Формулировки «не утверждено» / «передачи BDD нет» в прежнем README описывают предыдущую итерацию.

Проверена ветка `codex/design-v3-recovery`, HEAD `d7ef1ca`.
Read-only `git fetch origin main` подтвердил `origin/main = b60c647` (PR #59).
`git diff HEAD origin/main -- apps/web cases docs/product` пуст:
продуктовые исходники, сценарии и проверки здесь совпадают с проверенным main.
Checkout/reset, изменение продукта, тестов, CI, live-сервисов и browser QA не выполнялись.
Изменён только этот документ. Тесты не запускались: аудит не заявляет их прохождение.

Прочитаны корневые AGENTS/MAP/README, RULES, web AGENTS, актуальные behavior/design,
catalog-display/card-polish/security specs, cases.json, React/API-клиентские проверки
и соответствующие переходы App.tsx. Исторические reports не приняты за текущую спецификацию.

## Правило миграции

Сохранить стабильный ID, когда его смысл остаётся прежним; обновить Given/When/Then,
название в cases.json и связанный исполняемый тест в одном изменении.
«Retire» ниже означает убрать конкретное устаревшее ожидание, не удалить весь тест/ID
и не ослабить его остальные гарантии. Прежние отчёты остаются историей.
Новые ID назначить при реализации после проверки реестра; метки A34 ниже — локальная
матрица аудита, не занятые case IDs и не новые постоянные тесты.

## Матрица существующих требований и тестов

Пути в таблицах относительно корня репозитория; номера строк — проверенный HEAD.

| ID / точный тест или источник | Решение | Причина и необходимая замена |
|---|---|---|
| DEMO-003; SR-001/005; `App.test.tsx:204`, `SR-005 one photo candidate sends its receipt into search and reaches UI-007` | Revise; retire автоматический exact→карточка | Любое непустое фотоответное множество, включая единственный selectedId и высокий score, сначала список. Проверку multipart→receipt→search оставить; перед открытием UI-007 явно выбрать строку. Не менять API-001/selectedId на сервере ради этого UI-решения. |
| SR-005; `App.test.tsx:191`, `one unselected photo candidate uses a singular heading and one actionable row` | Keep + extend | Уже проверяет ручной выбор singleton. Добавить тот же результат с selectedId; отсутствие фиктивных альтернатив и корректное единственное число сохранить. |
| SR-001/002/003/004; `App.test.tsx:447`, `keeps multi-photo candidates ordered until a user chooses one, then restores the list`; `:492`, `handles the system Back event...` | Keep + extend | Порядок backend, выбор именно ID/года, возврат и отсутствие нового HTTP остаются. Проверить выбранный не первый ID, высокий score, положение списка и исходный снимок; selectedId не переставляет строки. |
| DEMO-005; UI-004/005; `App.test.tsx:280`, `cancellation returns home and keeps a photo only for explicit resume or deletion` | Revise; retire resume/delete-photo Home | Отмена теперь чистая Главная: убрать ожидания «Продолжить поиск» и «Удалить фото»; проверить их отсутствие, очистку фото/receipt/результата и abort. Сохранить запрет автоматического повтора. |
| UI-005; `App.test.tsx:315`, `ignores a late response after cancellation and resumes only on request` | Keep stale-response assertion; rename + extend | Тело этого теста фактически проверяет поздний ручной ответ после Back, а не возобновление фото. Сохранить эту защиту; отдельно покрыть late success/error загрузки и поиска по фото после Home. Название больше не должно обещать resume. |
| UI-022; `navigation.test.tsx:125`, `keeps a completed scan photo when Home opens without camera` | Revise; retire retained-photo assertions | Проверить чистую Главную из результатов/карточки и отсутствие getUserMedia. Нельзя оставить прежнюю фотографию просто скрытой с доступным старым receipt. |
| UI-022; `navigation.test.tsx:82`, `bottom Home returns to the start screen without starting camera capture`; `:104`, `explicit scan CTA...` | Keep; split scope clearly | Home не открывает камеру; CTA открывает, отказ имеет fallback; сохранённые вина не удаляются. Сохранение ручного query при повторном входе — отдельное прежнее свойство, не отменённое требованием очистить фото-попытку. Не превращать чистую Home в очистку localStorage. |
| DEMO-006, SR-005; `App.test.tsx:540`, `zero photo candidates offer the existing manual-search and reshoot fallback` | Extend; revise class-only assertions | Сейчас проверены ручной поиск и камера, но нет галереи. Добавить обе возможности замены фото; сохранить запрет выдуманных результатов. `primary`/`secondary` не являются самостоятельным поведением; точный вид берётся из Air. |
| SR-006; `App.test.tsx:570`, `declining candidates keeps the editable correction context without its photo` | Revise transition; keep manual isolation | Прямой отказ сейчас сразу ведёт в редактируемую коррекцию. Air сначала показывает восстановление «варианты не подошли», отличное от пустого ответа, с названием/камерой/галереей. Затем ручное поле не должно показывать фото; Back возвращает исходную ветку. Не терять её фото до принятой замены. |
| DEMO-009, UI-028; `App.test.tsx:691`, `distinguishes network and server failures and retries a retained receipt` | Keep + strengthen | Сеть фото покрыта; серверная половина — только manual GET. Нужны photo-search 503, timeout и невалидный ответ отдельно от пустого успеха; повтор использует receipt. После успешного retry ожидается список, затем явный выбор. |
| UI-005; `App.test.tsx:339`, `retry preserves scenario and query`; `:363`, `retry reuses a completed upload receipt` | Keep | Не загружать те же байты повторно, когда есть receipt. Обновить лишь helper/ожидание auto-open. Ошибка upload до receipt допускает повтор upload. |
| UI-011; `App.test.tsx:237/250`; `api.test.ts:40`, `distinguishes rejected image content from temporary upload failures` | Keep + extend origin | Невалидный файл — ошибка ввода, не no-match и не server-search error. При отмене/отказе от замены прежний контекст доступен; клиентская проверка не заменяет серверную. |
| UI-001/002/003/003A; `App.test.tsx:62/88/113/162/175` | Keep + extend | Реальная камера, JPEG capture, остановка текущего и поздно полученного stream, gallery и permission fallback остаются. Новый accepted capture сразу запускает upload/search без экрана подтверждения. |
| UI-026; `App.test.tsx:629`, `preview returns to its settled async origin instead of restoring stale loading` | Keep + extend | Закрытие просмотра сохраняет фактически завершившееся состояние. Список/scroll не сбрасываются, новый HTTP не отправляется. Проверить завершение запроса пока снимок открыт. |
| UI-027; `App.test.tsx:664`; `navigation.test.tsx:315`, `returns from a catalog card to the same list position`; `:328`, `a saved card correction cannot reuse candidates from an older search` | Keep + extend | Возврат соответствует фото/ручному поиску/каталогу/сохранённому, не глобальному последнему списку. Не повторять HTTP, не открывать клавиатуру насильно. |
| SR-007; `App.test.tsx:425`, `renders unknown fields and a broken catalog image without inventing metadata` | Revise; retire «Год не указан» | Неизвестный год исчезает из видимого текста и accessible name. Полное имя, честная заглушка и отсутствие пустых разделителей остаются. Год не извлекается из названия; известные данные не теряются. |
| CAT-004/005/007; `catalog-display-spec.md`, `catalog.test.tsx:90/104`; UI-029 `App.test.tsx:739` | Keep + extend | Только существующие структурированные поля; никакого дегустационного описания цвета вместо краткой категории. Источник/дата только реальные, честная reference/demo пометка сохраняется. Отсутствие сведений не заменяется заполнителями. |
| SR-008; `App.test.tsx:405`; REC001…REC005 `recommendations.test.tsx` | Keep | Ранжированный текстовый поиск и рекомендации сохраняют порядок и выделение лидера; исходный каталог/сохранённое не получают ложный рейтинг. Ошибка рекомендаций не заменяет карточку; stale response отменяется. |
| CAT-015…021; все тесты `live-search.test.tsx`; UI-024 `navigation.test.tsx:299` | Keep | 250ms, первый непустой символ, IME, явный submit, отмена, стабильность прежних карточек, серверная пагинация и возврат остаются. Air-макет с demo submit не основание вводить лишний шаг или убирать live search. |
| UI-008; `App.test.tsx:271`, `keeps the catalog hidden until the user asks for it`; `:528`, `does not send an empty manual query...` | Keep + extend idle art | Начальный ручной ввод остаётся сразу доступным. Добавить 2D alpha mascot в idle; он исчезает при загрузке/выдаче/пустом результате/ошибке и не превращается в промежуточный экран. Явный каталог и очистка уже выполненного поиска по CAT-017 не равны idle. |
| DESIGN-022; `design.test.tsx:182`, `places selected mascots only in their approved rendered app states` | Revise placement checks; keep alpha semantics | Текущий тест проверяет mascot по входу нижнего «Поиск», но не матрицу фаз ручного поиска. Добавить оба входа, alpha, отсутствие смешивания и mascot в результатах. Пиксельный размер файла >50KB не доказывает качество/прозрачность и не должен запрещать оптимизированный asset. |
| DESIGN-022; `design.test.tsx:221`, `gives photo no-match actions the approved full-width geometry` | Retire obsolete geometry; replace | Две full-width кнопки v2 не соответствуют Air с основным действием и лёгкой камерой/галереей. Сохранить доступность всех трёх выходов, touch targets и видимость на малом экране. |
| DESIGN-023/026; `card-polish.test.tsx:41/73`, `card-polish-spec.md`; SR-009 | Revise surfaces; keep content/order/images | Отменяются обязательная белая отдельная плитка, белый фон каждой фото-подложки, старый бордовый контур лидера. Air: единая поверхность, разделители, мягкая градация лидера. Остаются contain, full title, fallback, 76×132 / 56×98, backend order и контраст. |
| DESIGN-024/025; `card-polish.test.tsx:51/62`; UI-023 `navigation.test.tsx:274` | Keep semantics; adapt approved layout only | Именованные Back/Save, aria-pressed, сохранение ID, длинное название и fallback не удаляются ради новой композиции. Точный старый CSS hero/`sizes` меняется только с корректным новым srcset/layout, не произвольно. |
| DESIGN-013; `design.test.tsx:124`, `preserves the approved Atlas scan vector...` | Revise exact-vector contract | Air утверждает Phosphor Light. Убрать зависимость от старых path/stroke, проверить выбранную согласованную геометрию и имя действия; камера слева и scan справа CTA остаются. |
| DESIGN-001/002/003/004/006/014/017/018/019/020/022; `design.test.tsx` | Review numeric CSS assertions individually | Шрифты, доступные имена, области касания, focus, active navigation и адаптивность сохранить. Старые цвета/margin/radius/размеры сцены/иконки заменить только на конкретные Air решения. Не удалять весь design suite из-за substring mismatch. |
| DESIGN-005/007/008/010/011/012/015/016 | Keep invariants | Нет report controls в продукте; настоящая камера, видимый shutter, подсказка вне рамки, safe area, короткий/ландшафтный viewport, desktop shell. Изменение тонкости рамки не отменяет их. |
| UI-016…021; CAT-001…014; UI-012…015; UI-025; SEC-001…009 | Keep | Каталог, сохранённое, ошибки browser storage, PWA без обязательной установки, API versioning и безопасность не входят в отменяемое поведение. |

## Недостающие сценарии: проверяемая приёмка

| Аудит | Given / When / Then | Уровень и защита от слабой проверки |
|---|---|---|
| A34-01 Чистая Home | Из pending upload, pending search, slow, results, detail, empty, network/server error нажать Home; либо отменить поиск. Нет фото, resume, прежнего результата; все активные запросы abort; доставленные позже success/error ничего не меняют. Новый снимок создаёт новую попытку. | React: отложенные promises для обоих запросов, проверить signal и DOM после late resolve/reject. Проверить revokeObjectURL и отсутствие повторного HTTP. Сохранённое не очищается; не ожидать удаления уже приватно загруженного файла на сервере. |
| A34-02 Results first | Ответ: 0 / 1 / несколько; selectedId отсутствует / совпадает / указывает не на первый; допустимый высокий score. Ноль→empty; иначе список в исходном порядке; только первый лидер, ни одной auto-open карточки. | React table-driven, assert список до клика и правильный ID после. Валидность selectedId определяется действующим API-контрактом, не новым допущением UI. Не придумывать поля confidence для fixture. |
| A34-03 Все входы замены | Из results, empty, rejected-candidates, server error, offline нажать camera либо gallery. Отмена camera/пикера возвращает именно источник с прежними photo/receipt/list/query/scroll; принятый файл/снимок заменяет попытку и запускает поиск. | React переходы + browser нативный file picker/cancel. Cancel не моделировать пустым успешным upload. Невалидный выбор не стирает прежний контекст. Повторный выбор того же файла также работает. |
| A34-04 Гонки замены | Пока попытка A работает, принять B; A позже отдаёт receipt/успех/ошибку. Только B определяет UI и receipt; камера A остановлена. | Отложенные HTTP promises, отдельные receipts/ID, отрицательные assertions после обоих порядков завершения. |
| A34-05 Три исхода | Валидный 200 + []→нет совпадений; transport failure→сеть; 503/timeout/malformed response→ошибка сервиса. В ошибках нет утверждения об отсутствии вина. Retry с готовым receipt без upload; ошибка до receipt повторяет upload. | React + API-client validation. Отдельно photo pipeline, не подмена проверкой manual catalog. Abort по Home не показывается как offline/error. |
| A34-06 Loading | Запрос начат; линия ограничена прямоугольником исходного фото и не проходит по маскоту. Fast/slow ожидание завершается автоматически по реальному ответу, без Continue/демо-кнопки. | DOM ancestry + browser clipping/геометрия. fake timers и deferred response; проверить быстрый успех, поздний успех/ошибку и отмену. Демо-таймер не является производственным источником результата. |
| A34-07 Заметки | Пока loading/slow, заметка может сменяться; Pause останавливает только смену текста, кнопка меняет имя/состояние, resume восстанавливает. Поиск и его автоматическое завершение продолжаются. | fake timers, assert неизменный текст после pause и успешный переход по HTTP. Заметки — общие факты, не описание распознанного вина. |
| A34-08 Reduced motion | prefers-reduced-motion: reduce до входа и при изменении настройки: заметки не автолистаются; scan/slide/spinner не навязывают движение; статический status и все действия доступны. Уход очищает timers. | matchMedia stub + CSS и browser. Отключение анимаций не блокирует request completion и не скрывает статус. Modal photo/background tab не накапливают отложенные смены заметок. |
| A34-09 Поля | Полная/частичная карточка, неизвестный год/тип/крепость/источник; структурированный color отсутствует, description содержит длинный текст цвета. Показать только имеющиеся разрешённые краткие факты, без «Год не указан», «Нет данных» и разделителей-заполнителей. | DOM список + detail + accessible name. Категорию не добывать парсингом description/name; настоящие числовые диапазоны не усреднять. Не уничтожать полное каталожное описание в предназначенной для него области. |
| A34-10 Возврат | Открыть не первый результат после scroll/дополнительной страницы из photo/manual/catalog/saved; экранный Back и browser Back восстанавливают правильный источник, query, список, cursor/scroll, без лишнего HTTP и насильного focus. | Расширить SR-003/004, UI-027, CAT-020. Browser нужен для настоящего History/scroll; jsdom не доказывает физическую прокрутку. |
| A34-11 Ручной ввод | Оба входа сразу показывают поле и idle 2D alpha mascot. Первый ввод запускает CAT-015; loading/results/empty/error остаются под полем без mascot и отдельного шага. Очистка следует CAT-017. | DOM переходы по всем фазам, оба входа; сохранить CAT-016…021 и IME. Не добавлять запрос каталога лишь ради анимации. |
| A34-12 Light controls | Камера/галерея, Back/Save, pause, навигация доступны клавиатурой и reader; тонкий glyph не уменьшает область нажатия. На 320/360/390/430px, enlarged text и safe area нет перекрытия/overflow. | DOM accessible names, focus/pressed/current; browser measured targets: минимум 44 CSS px, сохранить существующий более строгий 48px там, где он задан; Air recovery 54×54 / компактный 48×52. Не путать размер SVG 25–30px с кнопкой. |

## Несогласованности документации, которые следует закрыть в реализации

1. `behavior-spec.md`: DEMO-003/005/006/009, UI-022, преамбула SR про сохранение
   одиночного exact-перехода, SR-001/005/006/007 и порядок кратких полей.
2. `cases/cases.json`: UI-004/005 сейчас прямо обещают retained-photo/resume;
   поменять title и при необходимости ссылки вместе с тестом, сохранив историю ID.
3. `apps/web/design-specs.md`: старый mascot placement, точная Atlas-геометрия,
   «Год не указан», бордовый контур/белые плитки; `card-polish-spec.md` DESIGN-023/026.
4. `design-v2-migration-plan.md`: retained context/resume и старые «Нет данных»
   сделать явно историческими, а не конкурирующим нормативным заданием.
5. Web AGENTS всё ещё предписывает выбранный v2: обновить ссылку на согласованную
   миграцию v3.4, сохранив upload/PWA/stable UI IDs. Общие контрактные границы не менять.

## Неослабляемые границы

- `API-010…014`, `SEC-001…009`, `UI-011`, `api.test.ts`, `request_security_test.go`,
  `security_test.go`: реальная проверка/лимиты upload, приватное хранение, receipt,
  непубличность фото, Origin/тип/размер/rate limits и разграничение ошибок остаются.
  Очистка UI не равна удалению серверного файла и не требует нового delete endpoint.
- `API-001…004` продолжают проверять форму/порядок/selectedId/empty/503 backend;
  results-first — политика отображения. Нельзя менять fixture на отсутствие selectedId,
  чтобы скрыть регрессию автоматического открытия.
- `CAT-001…014`: серверные страницы и курсоры, version/alias/provenance,
  запрет выдуманных полей, диапазоны, импорт/DB-инварианты сохраняются.
  `CAT-015…021`: debounce/IME/cancellation/stable rows/append/retry/back сохраняются.
- `UI-017…021`, `REC001…REC005`, PWA и конкурcный eval-контракт не отменены.
  UI-полировка не основание удалить сохранения/рекомендации или обещать offline ML.
- Новые fixtures синтетические, минимальные; пользовательские фото/каталог/секреты
  не копируются в Git. Mock доказывает границу UI, не доступность модели и не точность.

## Передача в реализацию и проверка

Сначала изменить канонические сценарии и case mapping; затем продукт и тесты по ним.
Заменять obsolete assertions адресно, оставляя соседние проверки upload/abort/ID/контекста.
Каждый новый тест должен падать на конкретном прежнем нарушении, а не проверять
наличие нового classname или копировать алгоритм компонента.

В реализации выполнить затронутые Vitest suites, production build и общий runner по README;
Go/security/catalog suites не исключать из общего прогона. Затем отдельное browser review
реального React-приложения: native gallery cancel, camera cleanup, small viewport/enlarged
text/safe area, keyboard, History Back, scan clipping и reduced motion.
Результат прототипа и наличие этой таблицы не заменяют эти свидетельства.
Аудит не требует публикации, миграции БД, запуска live-сервисов или изменения доступов.
