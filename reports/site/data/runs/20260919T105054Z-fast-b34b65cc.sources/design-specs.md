# Web scanner design specification

This app adapts the product screens in `design/wine-ux-atlas/site/design.css`. The atlas remains the visual source. These values make the implemented subset reviewable.

## Tokens

- Font: locally hosted Onest, weights 400, 500, 600, 700, 800, `font-display: swap`.
- Wine action color: `#742c46`; dark pressed state: `#572037`; paper: `#fffafd`.
- Primary scan action: minimum height 82 px, radius 18 px, three columns `42px minmax(0,1fr) 28px`.
- Primary camera glyph: 24 px. Trailing scan glyph: 28 px. Touch actions: at least 48 px where the atlas calls for comfortable controls.
- Cards and photo surfaces use the app's soft 14-20 px radius family.

## Responsive checkpoints

- 320 px: single column is the base layout. Controls remain within the viewport.
- 390 px: page side padding becomes 18 px.
- 360 px: the primary action uses `36px minmax(0,1fr) 28px`, 9 px gap, and 15 px by 12 px padding.
- 768 px: content remains one focused app column with 28 px vertical padding.
- 1280 px: the content column grows to at most 520 px. The interface is still the app, not a device mockup.

## Screens

- `UI-001`: welcome with scan, gallery, and manual search entries.
- `UI-002`: live rear-camera preview when available, centered target guidance, native capture fallback.
- `UI-003`: permission or unsupported-camera recovery.
- `UI-003A`: browser permission instructions with camera and gallery return paths.
- `UI-004`: local original photo, upload/search progress, long-wait copy, cancellation.
- `UI-005`: cancelled request, saved local photo, receipt-aware retry.
- `UI-006`: original-photo comparison and ranked candidates.
- `UI-007`: wine identity, correction, overview, description, and source.
- `UI-008`: manual search.
- `UI-009`: no catalog result and recovery.
- `UI-010`: upload/search/contract error and retry.
- `UI-011`: rejected local file type or size.
- `UI-016`: three-section navigation and initial catalog browse/filter.
- `UI-017`: save a validated wine snapshot and restore it after reload.
- `UI-018`: remove a saved wine and return to the saved-list empty state.
- `UI-019`: reject corrupt or duplicate saved snapshots with a recovery notice.
- `UI-020`: leaving catalog aborts its request; a late response cannot change section.
- `UI-021`: storage failure leaves the wine unsaved and reports the failure.

The client makes no quality or probability claims. The source tab identifies the current catalog content as prototype data.

Completed upload receipts are reused for retry. If cancellation races with an upload before its receipt reaches the browser, a retry can upload the file again because the API currently has no idempotency key.

## Camera viewport

The camera screen is bounded to `100dvh`. Its preview uses `minmax(0, 1fr)` and the video has no fixed minimum height, so browser bars reduce the preview before hiding the shutter. The action row remains in normal grid flow and includes bottom safe-area padding. At landscape heights up to 500 px, header, preview, and controls form three columns and the hint wraps inside the preview.

## camera-hint
DESIGN-012. Дано открытая камера. Когда показана подсказка «Нужная бутылка по центру», она находится в собственной строке под изображением, вне рамки. Рамка не пересекает текст при коротком/высоком экране и повороте. Уменьшается превью, затвор остаётся видимым. Быстрая проверка фиксирует реальную DOM-структуру и grid-контракт; геометрия проверяется отдельно в браузере.

## Welcome: точное соответствие двум элементам Atlas
DESIGN-013: SVG scan (углы + средняя линия) и focus-2 из assets/icons.js, не похожие замены. Scan28px/stroke1.55, target19px/stroke1.65.
DESIGN-014: подсказка без общего фона и padding, отступ сверху27px/снизу21px, gap12px. Плашка target34px/radius10; заголовок11px/500, текст10px/1.5 и оба предложения из макета. Проверки геометрии SVG и DOM текста быстрые; визуальная компоновка проверяется отдельно. Макет не меняется.

## Рамка на широком экране
DESIGN-015: Дано ширина от1024 CSS px. Когда открыто любое состояние приложения, оно находится по центру подложки в декоративной рамке телефона. При ширине до1023 включительно рамки и подложки нет; страница использует мобильный viewport. Определение по ширине, не user-agent; относится и к PWA.
DESIGN-016: Камера использует внутреннюю высоту рамки (до820px), превью сжимается, затвор остаётся внутри. Длинные экраны прокручиваются внутри рамки. Рамка не добавляет фиктивных системных кнопок или времени. Проверки CSS-контракта быстрые; реальная геометрия — отдельное браузерное ревью.

## Основная навигация и футер

DESIGN-017: Нижняя навигация находится отдельной строкой приложения, вне прокручиваемого `.app-content`. Три равные кнопки используют контурные Tabler SVG для сканера, поиска и закладок; нижний padding учитывает safe area.

DESIGN-018: Активный раздел помечен `aria-current="page"` и винным цветом. Футер «Информация о российских винах» использует Atlas: `margin-top:auto`, `padding:28px 0 0`, размер 11px, цвет `#766772`, выравнивание по центру.
