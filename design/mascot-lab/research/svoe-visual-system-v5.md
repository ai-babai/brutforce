# «Своё Вино»: visual-system audit v5

Captured 2026-09-19 (Europe/Moscow), read-only, from `https://vino-svoe.ru/`, `/wines`, and `/wines/ii-vino`. The 18+ confirmation was **not** clicked. Exact values below are either copied from current public CSS or read from browser computed styles; visual descriptions are explicitly marked as observations.

## Design character

The current site combines an editorial wine-magazine voice with a soft consumer product UI. It uses high-contrast serif display typography, a restrained system sans-serif for navigation and data, warm off-white surfaces, muted burgundy actions, large corner radii, and generous empty space. Photography is not treated as decoration around the edges: it is the dominant content in hero and product areas.

The useful translation for a dog mascot is material and compositional: warm ivory/cream fields, burgundy controls and accents, Playfair editorial titles, restrained line art, soft translucency, and photo-like lighting. Keep the existing «Своё Вино» logo intact; do not redraw it as a mascot or replace the brand mark.

## Verified palette

All values in this table occur in current site CSS unless marked "computed". Frequency is not a semantic guarantee; the role comes from named component rules and rendered inspection.

| Token / role | Value | Evidence |
|---|---:|---|
| Primary ink | `#2c2a28` | nav links, hero and section titles, wine-card text |
| Primary burgundy | `#8f3d42` | `.ui-button_primary`; rating accents; mobile search inner control |
| Burgundy hover | `#ab494f` | `.ui-button_primary:hover` |
| Burgundy pressed | `#723135` | `.ui-button_primary:active` |
| Dark brand accent | `#7b3528` | active nav; large round button |
| Warm card cream | `#fdf9ed` | `.wine-item`; wine-detail information panel |
| Pale blush / tertiary hover | `#f9f1f1` | `.ui-button_tertiary:hover` |
| Tertiary pressed | `#edd4d6` | `.ui-button_tertiary:active` |
| Muted text | `#857e79` | secondary UI text/icons |
| Light muted text | `#aea9a5` | wine producer labels |
| Fine neutral | `#d7d4d2` | borders/dividers in current CSS |
| Near-white page tint | `#fefdfa` | current CSS neutral surface |
| White | `#ffffff` / `#fff` | modal and image wells |
| Header glass | `#efdbc64d` | exact CSS: beige at alpha `0x4d` (~30%) plus blur |
| Mobile floating search | `#ffffffe6` | exact CSS: white at alpha `0xe6` (90%) |

Do not sample brand colors from screenshots as exact values: screenshots include compositing, blur, color management and background imagery. The values above come from CSS/computed styles.

## Typography

- Display family: `Playfair Display`, served by `/fonts/Playfair/PlayfairDisplay-VariableFont_wght.woff2`; variable weight font, exact public file archived in the evidence folder.
- UI/body family: `system-ui, -apple-system, sans-serif`.
- Desktop homepage H1: Playfair Display, `56px`, weight `400`, line-height `70px`, color `#2c2a28` (computed and CSS).
- Mobile homepage H1: Playfair Display, `42px`, weight `500`, line-height `52.5px` / `125%`, color `#2c2a28` (computed and CSS).
- Desktop section titles: Playfair Display, `42px`, weight `500`, line-height `52.5px`.
- Mobile section titles: commonly Playfair Display `36px/45px`, weight `500`; a similar-wines title is `32px/40px`.
- Product titles: system UI `16px/24px`, weight `600`.
- Producer labels: system UI `14px`, weight `400`, muted `#aea9a5`.

The serif is reserved for page and section hierarchy. Navigation, descriptions, buttons, filters, metadata and card names stay sans-serif. This contrast is a core part of the visual identity.

## Components and geometry

### Header

- Desktop header wrapper: `background-color:#efdbc64d`, `backdrop-filter:blur(10px)`, `border-radius:100px`, visual height `60px` from CSS `height:40px` plus vertical `padding:10px`, top margin `24px`, horizontal padding `24px` (`16px` at mobile rule).
- The logo sits left, navigation is centered, and search is a dark-burgundy circular control at right.
- Mobile keeps the capsule but reduces content to logo, search icon and burgundy hamburger capsule. Open mobile nav changes to `border-radius:24px` with stronger `blur(50px)`.

### Buttons

- Primary: `#8f3d42` background and 2px border, white text.
- Large rectangular button: exact `height:56px`, `padding:0 16px`, `border-radius:16px`; label is `16px/20px`, weight `600`.
- Primary interaction colors: hover `#ab494f`, active `#723135`.
- Tertiary: transparent at rest, burgundy text; hover `#f9f1f1`, active `#edd4d6`.
- Large round variant: `#7b3528`, `border-radius:999px`, `height:44px`, `padding:8px 16px`.
- Mobile floating wine search: white 90% surface, 1px white border, `border-radius:999px`, `padding:8px`; computed height `66px`, subtle multi-layer shadow.

### Wine cards

- Base `.wine-item`: `background-color:#fdf9ed`, flex column, `gap:16px`, overflow hidden, and gentle scale interaction (`1.025` hover / `.975` active).
- Catalog small variant: `border-radius:16px`, `padding:16px`, `gap:16px`; current desktop computed height was `421px` in the captured viewport.
- Homepage medium variant: `border-radius:32px`, `padding:20px`, `gap:12px`; current desktop computed height was `551px`.
- Product photography is isolated on the warm neutral field, generally centered and given much more space than text. Rating is a small pale-yellow pill near the top-left. Name is bold; winery is small and muted.

### Wine detail

- Mobile starts with centered wine name in Playfair `36px/45px`, winery in burgundy sans-serif, then a pale rating pill and a large centered bottle image.
- Information panel is `#fdf9ed`, `border-radius:24px`, `padding:32px 24px` on mobile.
- Desktop form of that panel uses a directional radius (`40px 0 0 40px`) and larger asymmetric padding; this creates joined editorial panels rather than a grid of generic cards.
- Image wells are white with `border-radius:16px`.

### 18+ modal (observed without confirming)

- Desktop card: white, computed `580px` wide, `border-radius:32px`; inner content `padding:48px`; primary CTA computed `484px × 56px` and radius `16px`.
- Desktop centers the card above a heavily blurred/dimmed page.
- Mobile changes the same modal to a bottom sheet with white background, large rounded top corners, centered Playfair `18+`, explanatory sans-serif copy, and a nearly full-width burgundy CTA.

## Background and image treatment

Visual observations from current renders:

- Homepage hero is a full-bleed vineyard scene with a pale sky used as clear space for the centered serif H1. The bottom edge has a very large rounded transition.
- The story module floats over the vineyard as a translucent, blurred warm panel. Within it, editorial imagery uses tall portrait cards with pronounced rounded corners and horizontal carousel cropping.
- Catalog background is near-white with very faint oversized botanical/grape line drawings. The pattern supports context without competing with product silhouettes.
- Product bottles are cut out or photographed on a uniform cream/white field with very little shadow and no heavy decorative framing.
- Burgundies stay muted and earthy rather than saturated red. Creams lean yellow/warm rather than gray.

For mascot art, use a warm, softly lit physical-material look (paper, ceramic, textile, or softly rendered fur) on a cream ground. Keep silhouette clarity high. Avoid neon wine red, black luxury gradients, hard glassmorphism, dense ornament and cartoon UI stickers; those do not match the observed system.

## Responsive behavior observed

- Desktop at `1440×1000`: full nav in one capsule; H1 `56px`; wide, landscape editorial module; catalog has left filters and four product cards across in the captured area.
- Mobile at `390×844`: compact capsule header; H1 `42px`; controls collapse; wine detail becomes a centered vertical product story with the bottle occupying the majority of the first screen.
- The 18+ layer is responsive: centered modal on desktop, bottom sheet on mobile.

## Practical adaptation rules for the dog mascot

1. Preserve the official logo and wordmark as a separate brand element.
2. Let the dog be the focal subject in the same way a bottle or editorial photo is: one clear object, large quiet margins, minimal secondary props.
3. Use `#fdf9ed` / `#fefdfa` ground, `#2c2a28` line/detail, and `#8f3d42` for one controlled accent (collar, small badge, CTA adjacency).
4. Match rounded framing to the actual component level: 16px for compact cards/buttons, 24–32px for large panels, capsule only for pills/header controls.
5. Pair Playfair headlines with system-sans labels; do not set long UI labels in the serif.
6. Favor soft botanical context, vineyard atmosphere, bottle-label restraint and shallow warm shadows. Do not paste grapes, bottles and wine glasses around every edge.

## Evidence and provenance

- Current rendered screenshots: `/tmp/svoe-v5/screenshots/`
  - `iab-home-desktop-1440x1000.jpg` — public homepage with delayed 18+ layer visible.
  - `iab-home-mobile-390x844.jpg` — responsive 18+ bottom sheet.
  - `iab-wines-desktop-1440x1000.jpg` — public catalog before the delayed age layer appeared; no confirmation action.
  - `iab-wine-detail-mobile-390x844.jpg` — public wine detail before the delayed age layer appeared; no confirmation action.
- Public source snapshots and browser computed-style JSON: `/tmp/svoe-v5/provenance/`.
- Limited, relevant public assets: `/tmp/svoe-v5/assets/` (entry/button/wine-card CSS, Playfair font, official logo SVG, 18+ SVG).
- Focused exact CSS excerpts: `/tmp/svoe-v5/provenance/css-component-snippets.txt`.
- `SHA256SUMS` records the collected files.
- `waf-blocked-*.png` under provenance document the factual boundary: direct local Playwright/Chrome navigation received the site's WAF block page. Those are not site-design references. The Codex in-app browser rendered the public pages, which supplied the valid screenshots listed above.

No account was used, no form was submitted, no age assertion was made, and no technical restriction was bypassed.
