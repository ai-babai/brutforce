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
- `UI-023`: result-header save action toggles its label, pressed state, and bookmark fill without moving its target.

The client makes no quality or probability claims. The source tab identifies the current catalog content as prototype data.

Completed upload receipts are reused for retry. If cancellation races with an upload before its receipt reaches the browser, a retry can upload the file again because the API currently has no idempotency key.

## Camera viewport

The camera screen is bounded to `100dvh`. Its preview uses `minmax(0, 1fr)` and the video has no fixed minimum height, so browser bars reduce the preview before hiding the shutter. The action row remains in normal grid flow and includes bottom safe-area padding. At landscape heights up to 500 px, header, preview, and controls form three columns and the hint wraps inside the preview.

## camera-hint
DESIGN-012. Дано открытая камера. Когда показана подсказка «Нужная бутылка по центру», она находится в собственной строке под изображением, вне рамки. Рамка не пересекает текст при коротком/высоком экране и повороте. Уменьшается превью, затвор остаётся видимым. Быстрая проверка фиксирует реальную DOM-структуру и grid-контракт; геометрия проверяется отдельно в браузере.

## Welcome: точное соответствие двум элементам Atlas
DESIGN-013: SVG scan (углы + средняя линия) и focus-2 из assets/icons.js, не похожие замены. Scan28px/stroke1.55, target19px/stroke1.65.
DESIGN-014: подсказка без общего фона и padding, отступ сверху27px/снизу21px, gap12px. Плашка target34px/radius10; заголовок11px/500, текст10px/1.5 и оба предложения из макета. Проверки геометрии SVG и DOM текста быстрые; визуальная компоновка проверяется отдельно. Макет не меняется.

## Welcome: бутылка в фоне hero

DESIGN-021: В `UI-001` используется тот же `concept-bottle.png`, что в Wine UX Atlas (SHA-256 файлов совпадает). Hero — относительный контейнер высотой 285 px с `overflow:hidden`; текстовый слой имеет `z-index:2`, ширину 220 px, верхний отступ 45 px, а описание — ширину до 205 px. Бутылка абсолютна на фоновом слое `z-index:1`: 160×240 px, `right:-35px`, `bottom:-45px`, `object-fit:contain`, `rotate(9deg)`. Смещение на 16 px ниже исходной координаты Atlas — запрошенная пользователем оптическая адаптация для равновесия композиции, а не утверждение о точной исходной координате Atlas. Поэтому нижняя и правая часть бутылки скрыты за границами hero перед началом кнопок, а не выглядит как отдельно стоящий наклонённый объект. Быстрая проверка фиксирует asset, слой, crop, геометрию и интервалы текста; визуальная сверка выполняется в браузере.

## Рамка на широком экране
DESIGN-015: Дано ширина от1024 CSS px. Когда открыто любое состояние приложения, оно находится по центру подложки в декоративной рамке телефона. При ширине до1023 включительно рамки и подложки нет; страница использует мобильный viewport. Определение по ширине, не user-agent; относится и к PWA.
DESIGN-016: Камера использует внутреннюю высоту рамки (до820px), превью сжимается, затвор остаётся внутри. Длинные экраны прокручиваются внутри рамки. Рамка не добавляет фиктивных системных кнопок или времени. Проверки CSS-контракта быстрые; реальная геометрия — отдельное браузерное ревью.

## Основная навигация и футер

DESIGN-017: Нижняя навигация находится отдельной строкой приложения, вне прокручиваемого `.app-content`. Три равные кнопки используют контурные Tabler SVG для сканера, поиска и закладок; нижний padding учитывает safe area.

DESIGN-018: Активный раздел помечен `aria-current="page"` и винным цветом. Футер «Информация о российских винах» использует Atlas: `margin-top:auto`, `padding:28px 0 0`, размер 11px, цвет `#766772`, выравнивание по центру.

## Сохранение в карточке

DESIGN-019: Действие сохранения находится справа в заголовке `UI-007`, а не отдельной широкой кнопкой под карточкой. Его область остаётся 92×48 CSS px в обоих состояниях: слева — кнопка «Назад» 48 px, заголовок имеет `min-width:0` и не выходит за экран шириной 320 px. Видимый текст — «Сохранить» или «Сохранено» (11 px), но доступное имя сохраняет прежние точные формулировки: «Сохранить вино» и «Удалить из сохранённых». Контурная `BookmarkSimple` становится залитой после успешного сохранения; действие без рамки и использует `#742c46`. Ошибка `localStorage` не меняет `aria-pressed`, подпись или иконку; сообщение под карточкой остаётся источником объяснения.

Решение принято по просьбе Макса для компактного знакомого паттерна сохранения, без заявления о точном копировании чужих интерфейсов. В качестве ориентиров просмотрены: [Airbnb: save a listing](https://www.airbnb.com/help/article/1236) и [Google Maps: save places](https://support.google.com/maps/answer/7280933?hl=en-AU).

DESIGN-020: Поле `UI-008` — единый контейнер с рамкой 1 px, радиусом 14 px и белым фоном. При фокусе на любом потомке рамка и кольцо появляются у контейнера; у текстового поля нет собственной рамки или внешнего outline. Кнопка отправки имеет минимум 48×48 px, винный фон, иконку 22 px и внутреннее кольцо при клавиатурном фокусе. Сетка `minmax(0,1fr) 52px` не выходит за ширину 320 px; после формы до списка остаётся 16 px. `UI-024` проверяет отправку по кнопке и клавишей Enter.

## Аудит нижней панели · 19.09.2026
При390×844: SVG22×22 CSSpx, stroke1.7px, подписи10px; область каждой кнопки124.66×54px, панель66px без дополнительного safe-area. Ошибка Сканера была в обработчике. Визуальное оформление по просьбе Макса пока сохранено.
[Android](https://support.google.com/accessibility/android/answer/7101858?hl=en): touch target48×48dp; [Apple](https://developer.apple.com/design/tips/):44×44pt, текст от11pt. [NN/g](https://www.nngroup.com/articles/icon-usability/): понятные подписи к иконкам. Native dp/pt и web CSSpx — разные системы; нужна проверка на устройстве. Кандидат следующего варианта: иконки24px и подписи11–12px. Это предложение, не утверждённый редизайн.
Панель — отдельный BottomNav, видимость управляется showNav в App.tsx. Можно убрать отдельной правкой; сейчас оставлена.
