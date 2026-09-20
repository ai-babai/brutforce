# Design acceptance checks

Explicitly requested by Maks on 2026-09-20 for the selected mascot edition. Tests are confined to the static design prototype, not production recognition or platform APIs.

Serve `../site` locally (for example Python HTTP server on port 8768). With Node, Playwright and Chrome already available:

```
DESIGN_URL=http://localhost:8768/ node flows.cjs
```

If Playwright is provided by a shared runtime, set `PLAYWRIGHT_MODULE` to its installed module path. No runtime or browser binaries are committed. Set DESIGN_URL to the public /v2/ URL to repeat the same acceptance checks after deployment.

Coverage: selected mascots only, 320/390 layouts and decoded images, all report scenarios, primary capture/error paths, cancellation with pending timer and retained photo, photo-preview returns, offline recovery without losing retry outcome, manual query/candidate preservation, no fabricated photo on text-only search, selected candidate vintage, successful reshoot after bad frame, report navigation and JS/HTTP errors.

Manual visual review remains necessary: 320/390/desktop, illustration/photograph separation, main actions visible and report links. The suite does not assert pixel snapshots or identify real wine. Gallery and permission pages are marked demonstrations of native/browser interactions. Timers only drive the prototype; they are not latency guarantees.

## Approved migration checks

Also run `node migration.cjs` with the same DESIGN_URL / PLAYWRIGHT_MODULE settings. UX-M01..10 cover the approved migration plan: explicit photo deletion; success/error arriving behind preview; query/list/scroll restoration; original correction identity; file/quality/server/network/match distinctions; catalog/Saved navigation, save/remove and viewport/phone-frame behavior; exact home copy; the simplified logo row; Home/Search/Saved labels and the separate Home versus camera actions. Tests use synthetic mockup data only and do not replace the application's reducer, API or storage tests.
