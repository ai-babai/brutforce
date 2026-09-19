# «Свое Вино» and Atlas mascot-composition notes

Date: 2026-09-19 (Europe/Moscow)

## Access and evidence

- Direct local Playwright/Chrome navigation to `https://vino-svoe.ru/`, `/wines`, and `/wines/ii-vino` returned WAF HTTP 403.
- The Codex in-app browser loaded the same public pages. No account, sign-up, camera permission, upload, or age confirmation was used.
- The delayed 18+ modal was left untouched. Three screenshots and provenance are in `site/assets/mascot-composition/` with the `svoe-` prefix.
- Publicly indexed page content confirms that `/wines` presents photo search as two primary actions — «Сканировать» and «Загрузить фото» — before the filterable wine grid. It is not relegated to a tiny header icon.

## Concrete cues from «Свое Вино»

1. The homepage uses a vineyard as a full-bleed environment. A large editorial card floats within it, combining title, copy, action and imagery. The visual does spatial work: it establishes culture and place instead of decorating a control.
2. The catalog is information-dense and product-led: scanner/upload entry, filters, then bottle cards. A mascot added here should support the scanner entry as a large contextual scene and disappear from repetitive product cards.
3. The mobile product page gives the bottle/image area most of the visual space, while name, producer and rating form a compact hierarchy above it. A mascot on a result page should stay subordinate to the bottle and metadata, for example as a cropped edge reaction, not as another equal-sized card.
4. The site language is warm cream, burgundy, serif display type, rounded panels, vineyard photography and wine-specific objects. For Atlas, the dog can inhabit this world through label, bottle, shelf and tasting-note gestures; a generic rounded avatar tile breaks that continuity.

## Current Atlas: start / waiting / missing

### Start

Current state: the dog is already closer to the right pattern than the other scenes. It is large, transparent/cropped and shares the title's pale vignette. It reads as part of the hero rather than a replacement icon.

Recommended static composition: keep the dog at roughly the present scale, but make the vignette a deliberate edge-to-edge hero field from the title block into the top of the CTA. Let the dog overlap or point toward the scan target, and remove any impression that it sits in a separate rectangle. The bottle/search purpose should be explicit in the pose: magnifier aimed at a label, nose/eyes tracking the label, or paw opening the camera frame. Do not add a separate mascot column.

### Waiting

Current state: the dog is reduced to an approximately 80–90 px object in a status row below a large bottle photo. The separate dog on the left and spinner/text on the right reads like avatar + utility icon and leaves unused horizontal and vertical space.

Recommended static composition: turn the lower edge of the photo into one joined scene. Use a 140–170 px transparent dog, cropped at the bottom, overlapping the photo by 24–40 px and looking through the magnifier at the bottle label. Put «Продолжаем поиск» and the conditional-time note in the same visual field, aligned to the dog's gaze. The dog should embody the ongoing action; the spinner can become a small secondary signal beside the text. This removes the empty split row and makes the wait state self-explanatory without animation.

### Missing

Current state: the dog sits in a rounded square above the heading. That makes it an app icon and creates a stack of disconnected blocks: mascot tile, heading/copy, bottle photo, then a large dead zone before actions.

Recommended static composition: remove the square tile. Place a 150–190 px transparent dog behind or beside the bottle-photo card, with part of the body clipped by its upper-right edge; its gaze should return toward the label or toward the fallback action. Bring the heading closer to this combined scene and move the primary fallback action upward with the content. The empty space should become purposeful overlap, not a larger illustration slot. The product photo remains primary, while the mascot explains the failed search.

## Static-first rule for the next mockup

- One large contextual mascot scene per state, never a mascot in place of a functional icon.
- The mascot may overlap/crop into a hero/photo surface; avoid adding a dedicated left/right column solely for it.
- Tie pose and gaze to a real object: label, bottle, camera frame, result card or fallback search.
- Preserve the bottle as the primary evidence on result and failure screens.
- Animation can later add breathing, magnifier glint or a small search-loop motion, but it should not be needed to make the static composition work.

## URLs inspected

- https://vino-svoe.ru/
- https://vino-svoe.ru/wines
- https://vino-svoe.ru/wines/ii-vino
- Local Atlas: http://127.0.0.1:8765/index.html?mascotPreview=1&scene=start&mode=hero#flows
- Local Atlas: http://127.0.0.1:8765/index.html?mascotPreview=1&scene=waiting&mode=hero#flows
- Local Atlas: http://127.0.0.1:8765/index.html?mascotPreview=1&scene=missing&mode=hero#flows
