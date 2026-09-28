# Web scanner design specification

Air 3.5 extends the selected Air design. Its product scenarios are [AIR-001…028](../../design/wine-ux-v3/air/behavior-v3.feature). Runtime loads `src/v2.css` and then `src/air.css`; the latter wins where the older dimensions below conflict. The older DESIGN checks remain regression evidence for retained behavior, not proof of final Air geometry. Browser review checks the rendered cascade separately.

Air camera at 320×640, 430×932, and 844×390: serif heading «Наведите на этикетку», live video using the available camera scene up to the action zone, direct capture and gallery actions, and a separate bottom navigation row. The video fills its scene width without card-like side borders; the frame overlays the video. Capture, gallery, Back, and navigation remain available without overlap or horizontal overflow. The main catalog shows 24 items first and loads further pages only on request; a 2038-record fixture checks bounded responses and traversal.

## Tokens

- Font: locally hosted Onest, weights 400, 500, 600, 700, and Playfair Display for headings, `font-display: swap`.
- Wine action color: `#8f3d42`; dark pressed state: `#723135`; paper: `#fefdfa`, cream: `#fdf9ed`.
- Primary scan action: minimum height 78 px, radius 18 px, three columns `39px minmax(0,1fr) 24px`.
- Primary camera glyph: 20 px inside a padded tile. Trailing scan glyph: 18 px. Navigation targets are at least 48 px; primary buttons at least 50 px and shutter 66 px. Compact secondary controls remain distinct from glyph dimensions.
- Cards and photo surfaces use the app's soft 14-20 px radius family.

## Responsive checkpoints

- 320 px: single column is the base layout. Controls remain within the viewport.
- 390 px: page side padding becomes 18 px.
- 360 px: the primary action uses `36px minmax(0,1fr) 24px`, 9 px gap, and 15 px by 12 px padding.
- 768 px: content remains one focused app column with 28 px vertical padding.
- 1024 px and wider: centered 410 px decorative phone shell; viewport below 1024 px has no phone border. Short-height rules shrink illustration/spacing, preserving the primary action.

## Screens

- `UI-001`: welcome with scan, gallery, and manual search entries.
- `UI-002`: live rear-camera preview when available, centered target guidance, native capture fallback.
- `UI-003`: permission or unsupported-camera recovery.
- `UI-003A`: browser permission instructions with camera and gallery return paths.
- `UI-004`: local original photo, upload/search progress, long-wait copy, cancellation.
- `UI-005` is a behavior case, not a separate screen: cancel returns to a clean UI-001 without photo/receipt/continuation; late responses do not reopen the path.
- `UI-006`: original-photo comparison and ranked candidates.
- `UI-007`: wine identity, immediate overview, optional closed description and direct source link; see Air 3.7 below.
- `UI-008`: manual search.
- `UI-009`: a successful empty photo search offers manual search, camera and gallery as distinct actions. A text search keeps its editable query. Human rejection of candidates has its own recovery state. Neither state invents a cause or wine card.
- `UI-010`: upload/search/contract error and retry.
- `UI-011`: rejected local file type/size or a server-rejected unreadable image. No unsupported diagnosis of blur/glare.
- `UI-016`: three-section navigation and initial catalog browse/filter.
- `UI-017`: save a validated wine snapshot and restore it after reload.
- `UI-018`: remove a saved wine and return to the saved-list empty state.
- `UI-019`: reject corrupt or duplicate saved snapshots with a recovery notice.
- `UI-020`: leaving catalog aborts its request; a late response cannot change section.
- `UI-021`: storage failure leaves the wine unsaved and reports the failure.
- `UI-023`: result-header save action toggles its label, pressed state, and bookmark fill without moving its target.

### Photo candidates · SR-001

`UI-006` preserves photo-search order from the backend. Every nonempty response, including a singleton with `selectedId`, shows a list until the user selects a row. The first row is marked as leader without a numeric confidence claim. Ranked text search and recommendations keep the same leader rule; unfiltered catalog and saved wines do not. Each row is one accessible target with the full name and known year. Compact facts come only from structured winery, name, year, type, sugar and strength; missing values are omitted without guessing from description. The full card retains its save and recommendations; Air 3.7 specifies the rest below. A missing or broken image has an accessible placeholder. At 320/360/390/430 px and 200% text, rows wrap inside the viewport. Air uses one list surface with dividers and a soft leader gradient; the white tiles and burgundy outline in FE-057 are historical.

The client makes no quality or probability claims. A demo/reference label reflects its actual response, independently of a catalog source URL.

### Air 3.7 · FE-088 · UI-007

The [observable scenarios](../../design/wine-ux-v3/air37/behavior-v37.feature) supersede the former card tabs and correction row. The bottle occupies the left shelf column; only structured sugar, valid alcohol and nonempty region appear as unboxed Onest term/value pairs with the approved icons to its right. A positive integer `year` appears beside the winery on one line when space permits, otherwise the winery has no separator; the overview retains «Год не указан». Never infer year from the title. A safe http(s) `sourceUrl` produces a directly clickable «Открыть на сайте «Своё Вино» ↗» link in a new isolated tab; no URL means no link. The main TEST UI has no photo-feedback controls, including when the search response contains `feedbackToken`; the prior release remains separate for annotation. Overview rows are immediate. A nonempty description alone produces a closed «О вкусе и сочетаниях» disclosure after the summary. Back leads to the originating list, where another candidate can be chosen. Tests: `src/air-v37.test.tsx`, `node air37.browser.mjs` from `apps/web`; mocked transport checks UI and layout, not ML or physical camera.

В блоке «Вам также может подойти» у всех похожих вин одна ширина строки, размер бутылки и заголовка, отступы и минимальная высота. Первый сохраняет отметку «Наиболее похожее» и мягкую цветовую подложку, но не увеличивается. Это уточнение относится только к рекомендациям на `UI-007`, не к ранжированной выдаче `UI-006` и не к поиску.

Completed upload receipts are reused for retry. If cancellation races with an upload before its receipt reaches the browser, a retry can upload the file again because the API currently has no idempotency key.

## Camera viewport

The camera screen uses the height available inside the app, including the desktop phone shell. The live video fills the remaining camera scene after header and action space; no fixed 180–390 px viewfinder target remains. Browser bars and safe areas reduce the scene before hiding capture, gallery, Back, or navigation. At landscape heights up to 500 px, header, preview, and controls may form three columns; the video still fills the preview scene and the hint does not cover the target frame. Verify the final rendered rectangles in a browser.

## camera-hint
DESIGN-012. Дано открытая камера. Когда показана подсказка «Нужная бутылка по центру», она находится в собственной строке под изображением, вне рамки. Рамка не пересекает текст при коротком/высоком экране и повороте. Уменьшается превью, затвор остаётся видимым. Быстрая проверка фиксирует реальную DOM-структуру и grid-контракт; геометрия проверяется отдельно в браузере.

## Welcome: значок сканирования и подсказка
DESIGN-013: Air uses Phosphor Light scan geometry. The camera icon stays at the left of the main CTA and the scan icon at the right. The v2 exact SVG path and stroke are historical.
DESIGN-014: в принятом FE-027 варианте Г подсказка — центрированная тёплая карточка с точным текстом «Этикетка целиком, нужная бутылка по центру.», `padding` 12×14px, границей `#eadfd4`, радиусом 14px и фоном `#fcf7ef`. Естественный перенос и геометрия проверяются отдельно в браузере.

## Welcome: selected mascot composition

DESIGN-022 / FE-027: `UI-001` uses the selected Wine UX 2.0 logo and one continuous `#fbf6ec` field from page top through header, hero and centered alpha mascot. The full-width Playfair title «Какое вино перед вами?» has no forced break, uses balanced natural wrapping (36px at 390px, 32px at 320px), and the explanation is centered. The mascot is 260px in the standard mobile composition, `contain`/`center bottom`; short heights reduce the scene in normal scroll flow so CTA and navigation stay reachable. The header has no rounded, translucent, or colored pill surface. The home scene keeps its descriptive alt text. The functional secondary scenes use the same selected edition: walk during photo search, thoughtful counter for no match, cellar for an empty manual search, and offline for a connection failure. These images are decorative and hidden from assistive technology. In `UI-009`, the counter scene is placed before the action panel in normal flow and does not overlap action labels.

The mascot is never rendered over the real camera, permission guidance, gallery/native file picker, expanded photograph, candidates, saved wines, or wine facts. The local app stores 90-quality WebP renditions of the 1536×1024 selected assets. Their original source SHA-256 values and conversion command are recorded in `assets-v2-provenance.md`; artwork source is selected design revision `29874e7`.

At 390 px, the mascot panel is 260 px; at 360 px it is 220 px. Short-height overrides reduce it further; the viewport test must use the final cascade. It remains in normal document flow so the primary action is reachable at 320 px. Fast tests verify assets, alt handling, typography and visual tokens. Browser review verifies crops and action visibility at 320×568, 390×844, 844×390 and desktop frame sizes.

## Рамка на широком экране
DESIGN-015: Дано ширина от1024 CSS px. Когда открыто любое состояние приложения, оно находится по центру подложки в декоративной рамке телефона. При ширине до1023 включительно рамки и подложки нет; страница использует мобильный viewport. Определение по ширине, не user-agent; относится и к PWA.
DESIGN-016: Камера использует внутреннюю высоту рамки (до820px), превью сжимается, затвор остаётся внутри. Длинные экраны прокручиваются внутри рамки. Рамка не добавляет фиктивных системных кнопок или времени. Проверки CSS-контракта быстрые; реальная геометрия — отдельное браузерное ревью.

## Основная навигация и футер

DESIGN-017: Нижняя навигация находится отдельной строкой приложения, вне прокручиваемого `.app-content`. Три равные кнопки используют контурные Tabler SVG для сканера, поиска и закладок; нижний padding учитывает safe area.

DESIGN-018: Активный раздел помечен `aria-current="page"` и винным цветом. Футер «Информация о российских винах» использует Atlas: `margin-top:auto`, `padding:28px 0 0`, размер 11px, цвет `#766772`, выравнивание по центру.

AIR-027: Одна фоновая подложка перемещается между тремя вкладками вслед за активным разделом. При быстрой смене она завершается на текущей вкладке; при `prefers-reduced-motion: reduce` перемещается сразу. Видимый раздел и `aria-current` совпадают с конечной позицией.

AIR-028: Крупные винные primary CTA с текстом используют одну вычисленную типографику во всех экранах: `font-family`, `font-size`, `font-weight`, `line-height`. На 320 CSS px и при 200% текста подписи не обрезаются и не перекрывают иконки или навигацию. Icon-only, вторичные и nav-кнопки не входят в это правило.

## Сохранение в карточке

DESIGN-019: Действие сохранения находится справа в заголовке `UI-007`, а не отдельной широкой кнопкой под карточкой. Его область остаётся 92×48 CSS px в обоих состояниях: слева — кнопка «Назад» 48 px, заголовок имеет `min-width:0` и не выходит за экран шириной 320 px. Видимый текст — «Сохранить» или «Сохранено» (11 px), но доступное имя сохраняет прежние точные формулировки: «Сохранить вино» и «Удалить из сохранённых». Контурная `BookmarkSimple` становится залитой после успешного сохранения; действие без рамки и использует `#742c46`. Ошибка `localStorage` не меняет `aria-pressed`, подпись или иконку; сообщение под карточкой остаётся источником объяснения. FE-057 уточняет верхний отступ страницы и минимальные цели в [DESIGN-024](../../docs/product/card-polish-spec.md#сценарии).

Решение принято по просьбе Макса для компактного знакомого паттерна сохранения, без заявления о точном копировании чужих интерфейсов. В качестве ориентиров просмотрены: [Airbnb: save a listing](https://www.airbnb.com/help/article/1236) и [Google Maps: save places](https://support.google.com/maps/answer/7280933?hl=en-AU).

DESIGN-020: Поле `UI-008` — единый контейнер с рамкой 1 px, радиусом 14 px и белым фоном. При фокусе на любом потомке рамка и кольцо появляются у контейнера; у текстового поля нет собственной рамки или внешнего outline. Кнопка отправки имеет минимум 48×48 px, винный фон, иконку 22 px и внутреннее кольцо при клавиатурном фокусе. Сетка `minmax(0,1fr) 52px` не выходит за ширину 320 px; после формы до списка остаётся 16 px. `UI-024` проверяет отправку по кнопке и клавишей Enter.

## Аудит нижней панели · 19.09.2026
При390×844: SVG22×22 CSSpx, stroke1.7px, подписи10px; область каждой кнопки124.66×54px, панель66px без дополнительного safe-area. Ошибка Сканера была в обработчике. Визуальное оформление по просьбе Макса пока сохранено.
[Android](https://support.google.com/accessibility/android/answer/7101858?hl=en): touch target48×48dp; [Apple](https://developer.apple.com/design/tips/):44×44pt, текст от11pt. [NN/g](https://www.nngroup.com/articles/icon-usability/): понятные подписи к иконкам. Native dp/pt и web CSSpx — разные системы; нужна проверка на устройстве. Кандидат следующего варианта: иконки24px и подписи11–12px. Это предложение, не утверждённый редизайн.
Панель — отдельный BottomNav, видимость управляется showNav в App.tsx. Можно убрать отдельной правкой; сейчас оставлена.

### Уточнение главной и навигации — Issue #24, 20.09.2026

В шапке только логотип с подписью банка, без отдельного «Поиск по этикетке». Нижняя панель: Главная (домик), Поиск, Сохранённое; активный пункт соответствует разделу. Главная не является кнопкой камеры. Маскот главной использует `mascot-hold-2d-alpha.webp` с настоящей прозрачностью, на общем фоне #fbf6ec, без смешивания цветов; старый файл не удаляется из истории. DESIGN-022 проверяет выбранный asset и alpha-флаг WebP, отсутствие подписи; геометрия проверяется отдельно в браузере.

### All mascot scenes: real transparency (design 4a3615f)
Given home, manual search, waiting, no-match or offline, the selected mascot uses an alpha WebP. Transparent source background is preserved; opaque character and props remain visible. Normal composition, no multiply or CSS mask to simulate transparency. No behavioral changes.

FE-027 responsive acceptance: 320×568 normal-text CTA must be fully above bottom navigation; short-height art is160px. At enlarged text sizes the content scrolls, action labels wrap inside their buttons, icons remain visible, no horizontal overflow. Fast checks cover wrapping rules; rendered geometry is verified separately.


## FE-035 · Выдача фото, вариант В; уточнение FE-057

SR-001…009: первый результат выделен мягкой градацией внутри общей поверхности;
бейдж «Наиболее похожее» без процента уверенности. Остальные строки компактны.
Фото лидера 76×132, остальных ранжированных строк 56×98 CSS px, contain; заголовки 18/14 px. FE-057 меняет только поверхность: [DESIGN-026](../../docs/product/card-polish-spec.md#сценарии).
Имя/линейка → производитель → год → известные цвет/сахар. Полные названия,
неизвестный год скрыт, сломанное фото заменяется нейтральной заглушкой.
Вся строка — кнопка; focus visible; бейдж ограничен шириной и переносится при
увеличении текста. Для одного фото-кандидата — единственное число в заголовке.
Быстрые CSS проверки не измеряют геометрию: [браузерное ревью](../../docs/product/reviews/fe-035/README.md).
