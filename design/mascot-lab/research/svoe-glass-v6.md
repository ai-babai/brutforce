# «Своё Вино»: glass and layered-surface audit v6

Read-only follow-up captured 2026-09-20. Sources are the current public HTML/CSS/JS from `vino-svoe.ru` plus the valid browser renders collected in v5. The 18+ action was not clicked. Values labeled exact are copied from current CSS; observations from screenshots are labeled as such.

## The short answer

The site does **not** apply glass everywhere. Its system separates four surface types:

1. **True frosted glass:** translucent fill plus `backdrop-filter`. Used for the closed/open header, homepage story panel, mobile floating search, and modal overlay.
2. **Translucent tint without blur:** alpha fill over imagery. Used for inactive homepage chips.
3. **Opaque surfaces with a nominal blur rule:** visually opaque, so the blur contributes little or nothing. Current tooltip and active-chip rules fall here.
4. **Opaque content surfaces:** white modal/bottom sheet and cream result/product cards. These protect text and product recognition.

This distinction should be preserved in the wine-scan experience. Glass should mark floating navigation and transitional layers; camera controls and recognition results need stable, opaque surfaces.

## Exact current rules

### Closed header: true glass

Base rule, all sizes:

```css
.core-header__wrapper {
  backdrop-filter: blur(10px);
  background-color: #efdbc64d;
  border-radius: 100px;
  height: 40px;
  margin-top: 24px;
  padding: 10px 24px;
  overflow: hidden;
}
```

At `@media only screen and (width <= 767px)`, horizontal padding changes to `10px 16px`. The visual outer height is 60px because the 40px content height has 10px top and bottom padding. The fill alpha is `0x4d` = 77/255, about 30%; therefore the `blur(10px)` is materially visible over photography.

Use this on the scan home header and results header. Preserve the pill silhouette and warm tint; do not turn it into a colorless iOS-style glass bar.

### Open mobile menu: stronger true glass

Modifier rule:

```css
.core-header__wrapper--open {
  backdrop-filter: blur(50px);
  border-radius: 24px;
  height: calc(100vh - 62px);
  margin: 8px -16px 0;
  padding: 24px;
}
```

The modifier does not replace `background-color`, so it inherits the base `#efdbc64d` tint. It transitions height, margin, padding, blur and radius. On mobile it becomes a nearly full-height warm frosted panel while retaining a small page margin.

Use this pattern only for full navigation or a similarly broad mode switch. It is too strong and too spatially dominant for a camera instruction card or result detail.

### Mobile floating wine search: almost opaque glass

The current element carries `no-tablet no-desktop`, so it is intended for the mobile range below the tablet breakpoint. Exact rule:

```css
.core-header__mob-search-btn {
  color: #2c2a28;
  backdrop-filter: blur(5px);
  background: #ffffffe6;
  border: 1px solid #fff;
  border-radius: 999px;
  padding: 8px;
  position: fixed;
  bottom: 24px;
  left: 24px;
  right: 24px;
  transform: translateY(90px);
  box-shadow:
    0 1px 2px #6c550f1a,
    0 4px 4px #6c550f0d,
    0 0 20px #6c550f1a;
}
.core-header__mob-search-btn_show { transform: translateY(0); }
```

Computed height in the v5 mobile browser render was 66px. `#ffffffe6` is 90% white, so this reads as a stable white dock with a trace of background integration, rather than obvious glass. Its inner burgundy camera control is an opaque 48px circle (`#8f3d42`, radius `999px`).

This is the strongest reference for the scan-home camera CTA: fixed at 24px from the sides and bottom, mostly opaque, one burgundy 48px action, centered label. Preserve the 5px blur but do not lower the white opacity to make it more spectacular.

### Homepage story panel: warm editorial glass

Exact base/mobile rule:

```css
.container-smooth {
  backdrop-filter: blur(5px);
  background-color: #efdbc6ba;
  border-radius: 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  margin: 0 auto;
  padding: 24px;
}
```

`#efdbc6ba` has alpha `0xba` = 186/255, about 73%. It is much denser than the header, and the blur is only 5px. The result is a readable warm panel that still carries vineyard color and light through it.

Responsive rules:

- `width >= 768px`: `gap:24px`, `max-width:calc(100% - 48px)`, `padding:48px`.
- `width >= 1024px`: row layout, `width:1200px`, `padding:48px 0 48px 48px`.
- Slider offsets: mobile `margin-left/right:-24px`; at `>=768px`, `-48px`; at `>=1024px`, it becomes `max-width:calc(100% - 352px)` with `margin:-48px 0 -48px -24px`.

Use this density for a single editorial explanation on scan home, such as a short «how it works» carousel. Do not use it for every result card.

### Homepage chips: translucent, not necessarily glass

Inactive chip:

```css
.home-chip {
  background-color: #fdf9edcc;
  border: 1px solid #ffffff4d;
  border-radius: 999px;
  height: 32px;
  padding: 0 12px;
}
```

This rule has no `backdrop-filter`. The cream is 80% opaque and the white border is 30% opaque. Classify it as a translucent tint, not frosted glass.

The active chip declares `backdrop-filter:blur(5px)` but also uses opaque `#8f3d42`. Since the fill is opaque, the backdrop blur is not visibly useful. Treat the active state as a solid burgundy pill.

### Modal overlay and bottom sheet: blur outside, opacity inside

The shared modal overlay is true dark glass:

```css
.ui-overlay {
  backdrop-filter: blur(10px);
  background-color: #00000080;
}
```

The sheet itself is fully opaque:

```css
.ui-modal-bottom-sheet {
  background-color: #fff;
  border-radius: 32px 32px 0 0;
  width: 100vw;
  height: 100%;
  padding-bottom: 24px;
  bottom: -24px;
}
.ui-modal-bottom-sheet_content-height { max-height: fit-content; }
.ui-modal-bottom-sheet_expandable { height: 50vh; }
.ui-modal-bottom-sheet_expanded { height: 100%; }
```

The desktop modal card is also opaque white with `border-radius:32px`. The transparent `without-styles` variant is explicitly separate.

The age component requests the bottom-sheet presentation for `xs` and `sm`. Current JS breakpoint mapping is:

- `xs`: width below 576px.
- `sm`: 576px through below 768px.
- `md`: 768px through below 1024px.
- `lg`: 1024px through below 1200px.
- `xl`: 1200px and above.

The age sheet content uses `height:406px; padding:24px 32px` on mobile. At `width >= 768px`, it changes to a centered card `width:580px; height:auto; padding:48px`.

For scan results, use this same separation: dark blurred overlay behind an opaque result/action sheet. Do not make the sheet translucent; bottle names, vintages, confidence and action buttons need reliable contrast.

### Tooltips: technically blurred, visually opaque

```css
.wine-tooltip {
  backdrop-filter: blur(2.5px);
  background: #fefdfa;
  border-radius: 8px;
  width: 256px;
  padding: 8px 12px;
  box-shadow:
    0 6px 12px #2c2a2812,
    0 0 6px #2c2a280f,
    0 0 2px #2c2a280f;
}
```

Because `#fefdfa` is opaque, the backdrop blur cannot materially show through. Implement this as an opaque warm-white tooltip. Do not copy the blur merely because it exists in CSS.

## Actionable mapping for the wine-scan flow

| Surface | Recommended treatment | Why |
|---|---|---|
| Scan-home header | Header glass: `#efdbc64d`, blur 10px, capsule | Direct match to current mobile brand navigation |
| Scan-home camera CTA | Floating dock: 90% white, blur 5px, white border, soft shadow, burgundy 48px action | Current site already uses this exact component to invite wine search |
| Scan-home explainer | At most one `container-smooth` panel: warm 73% beige, blur 5px, radius 40px | Editorial brand connection without covering the whole page in glass |
| Camera viewfinder | Keep image optically clear; use small opaque or near-opaque controls at edges | Backdrop blur over the recognition target conflicts with the scanning task |
| Camera guidance | Prefer a compact 90% white instruction capsule; dark translucent edge scrim is acceptable | Stable text and framing while the live image remains readable |
| Camera capture action | Solid burgundy `#8f3d42` circle/button | Mirrors the current inner camera control and preserves action salience |
| Recognition loading | One small near-opaque floating status capsule; no full frosted layer | Keeps camera feedback connected to the live image |
| Results page header | Reuse closed header glass | Provides continuity from scan home |
| Result list/cards | Opaque `#fdf9ed` cards, 16–24px radius | Matches wine cards and protects label photography and metadata |
| Result detail/actions | Opaque white/cream bottom sheet, radius `32px 32px 0 0` | Matches current modal grammar and improves dense information contrast |
| Background behind sheet | `#00000080` plus blur 10px | This is where the current site puts the dramatic blur |
| Filter/status chips | Inactive cream at 80% alpha, no blur; active solid burgundy | Matches current chip semantics; avoids unnecessary compositing |

## Constraints for implementation

- Do not apply blur to a container unless it has a translucent fill and meaningful content behind it. The tooltip rule shows why a declared blur can still be visually irrelevant.
- Keep the camera preview itself unblurred. If a sheet is open, blur/dim the preview through a separate overlay rather than blurring the sheet.
- Limit simultaneous glass layers. Recommended maximum on scan home: header plus floating camera dock; add the editorial panel only lower in the scroll.
- Preserve warm tints. Neutral gray or blue glass would break the relationship to the vineyard and cream-card system.
- Keep opaque result cards. Glass behind bottle labels, vintage text and confidence indicators reduces recognition and accessibility.
- Use the site's measured radii by role: 100px/999px for capsules, 40px for the editorial glass panel, 32px for modal sheets, 24px for open navigation, 16px for compact cards and primary rectangular buttons.
- Use the existing transition intent: the floating dock enters from `translateY(90px)`; the open menu morphs height/radius/blur rather than appearing as a separate sheet.

## Evidence bundle

- `/tmp/svoe-glass-v6/assets/entry.CcAo-ZK4.css` — current global responsive utilities.
- `/tmp/svoe-glass-v6/assets/UiModal.CrLdwUi3.css` — exact overlay, card and bottom-sheet rules.
- `/tmp/svoe-glass-v6/assets/AppModalProofOfAge.DuHbB1tw.css` — exact age-content sizing and `>=768px` switch.
- `/tmp/svoe-glass-v6/assets/RqfpLLZa.js` — component declaration requesting bottom sheet at `xs` and `sm`.
- `/tmp/svoe-glass-v6/assets/Qij-SWrx.js` — current breakpoint mapping and page integration.
- `/tmp/svoe-glass-v6/assets/DL9YfRCP.js` — modal component structure.
- `/tmp/svoe-glass-v6/provenance/exact-rules.txt` — selected header/story/search/chip/tooltip rules with media context.
- `/tmp/svoe-glass-v6/screenshots/mobile-age-sheet-390x844.jpg` — current mobile opaque sheet over blurred/dimmed page; no confirmation action.
- `/tmp/svoe-glass-v6/screenshots/mobile-wine-detail-header-390x844.jpg` — current mobile header and product composition before the delayed gate appeared.
- `/tmp/svoe-glass-v6/screenshots/desktop-home-story-glass-1440x1000.png` — current homepage hero/story panel reference captured before the delayed gate.

Browser rendering was not newly available in the follow-up session, so the report uses the valid current renders captured on 2026-09-19 and freshly re-read public assets on 2026-09-20. No gate was bypassed, no account was used, and no repository file was modified.
