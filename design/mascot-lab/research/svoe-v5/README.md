# Provenance

Collected read-only on 2026-09-19 (Europe/Moscow) from the public website `https://vino-svoe.ru`.

- `home.html`, `wines.html`, `ii-vino.html`: public server-rendered HTML retrieved with HTTP GET.
- `iab-*-computed.json`: computed styles read from the corresponding public render in the Codex in-app browser.
- `css-component-snippets.txt`: limited rules extracted verbatim from the current server-rendered CSS; selectors retain build scope attributes.
- `render-inspection.jsonl` and `waf-blocked-*`: direct Playwright/Chrome was rejected by the site's WAF with HTTP 403. These are boundary evidence, not visual references.
- Valid current screenshots are in `../screenshots/`; the browser never clicked the `Подтверждаю` button.
- Public asset URLs used: `/_nuxt/entry.CcAo-ZK4.css`, `/_nuxt/UiButton.BumBsR97.css`, `/_nuxt/WineItem.D1J_HiaW.css`, `/fonts/Playfair/PlayfairDisplay-VariableFont_wght.woff2`, `/svg/logo/svoe-vino-logo.svg`, `/svg/eighteen-plus.svg`.

No exact color was inferred from screenshot pixels. Palette hex values in the report come from CSS or browser computed styles.
