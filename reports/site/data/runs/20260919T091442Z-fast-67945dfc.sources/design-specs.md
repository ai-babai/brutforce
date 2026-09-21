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
- 390 px: page side padding becomes 18 px; the primary action uses `36px minmax(0,1fr) 28px`.
- 768 px: content remains one focused app column with 28 px vertical padding.
- 1280 px: the content column grows to at most 520 px. The interface is still the app, not a device mockup.

## Screens

- `UI-001`: welcome with scan, gallery, and manual search entries.
- `UI-002`: live rear-camera preview when available, centered target guidance, native capture fallback.
- `UI-003`: permission or unsupported-camera recovery.
- `UI-004`: local original photo, upload/search progress, long-wait copy, cancellation.
- `UI-005`: cancelled request, saved local photo, receipt-aware retry.
- `UI-006`: original-photo comparison and ranked candidates.
- `UI-007`: wine identity, correction, overview, description, and source.
- `UI-008`: manual search.
- `UI-009`: no catalog result and recovery.
- `UI-010`: upload/search/contract error and retry.
- `UI-011`: rejected local file type or size.

The client makes no quality or probability claims. The source tab identifies the current catalog content as prototype data.

Completed upload receipts are reused for retry. If cancellation races with an upload before its receipt reaches the browser, a retry can upload the file again because the API currently has no idempotency key.
