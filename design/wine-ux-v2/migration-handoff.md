# Approved migration UX - design handoff

2026-09-20. Initiator: Maks, delegated from session 01a0b128-3ad8-72e1-ad67-4ade90613061 to design session 01a0aa4a-9655-7c12-8c1e-fe02a7fcc299. Based on docs/product/design-v2-migration-plan.md, b73baf6 in codex/behavior-demo. This change edits static design only. No apps/web/API/storage code was changed. Publication metadata continues to describe the previously deployed edition until an explicit static-report release.

## Accepted decisions and examples

1. Cancel an active photo search -> Home, retained-photo controls: Continue search / View photo / Delete photo. No automatic restart. Delete invalidates any pending simulated response and removes the retained-photo actions. Resume reuses the current mock photo ID; another capture obtains a new one.
2. Photo preview retains the origin and does not stop the request. If the request finishes while preview is open, the preview remains open with a short status. Closing shows the fresh result/error, not stale loading and not a second request. If still pending, it returns to the same pending search.
3. Manual search keeps the query, result list and inner/page scroll when returning from a card. Empty search has a short hint and explicit catalog access. Catalog opens the same candidate component; missing text results keep the query editable. Text-only paths never synthesize a user photo.
4. The explicit 'Not this wine' action captures the original identity/year, detail tab, return target and whether the photo relates to that result. Candidate/manual detours can return to that exact card. A newly selected wine remains separate from the original correction context; choosing it does not overwrite the correction origin. Normal Back to candidates is not reinterpreted as a new correction action. Saved/catalog/text-only cards go directly to manual search on correction; unrelated candidates from a retained scan are never shown. Empty manual search places its input before the hint/catalog entry and mascot.
5. offline = network unavailable; servererror = service response failed; missing = no suitable match. Only the first two offer retry of the retained photo. An unknown match is not evidence of a server failure or poor image quality.
6. unreadable = image file cannot be opened, never sent to search in this demo. badphoto = explicit trustworthy quality signal that the label is unreadable; no assumed glare cause. missing = no match with unknown cause. Each has a different explanation and recovery. New valid file/reshoot can leave an error state.
7. Preserve Home / Search / Saved bottom navigation. Home uses a house icon and always opens the start screen; it never opens the camera. Bottom navigation never opens the camera; explicit capture and reshoot actions do. Hide bottom navigation on camera. Save/remove is demonstrated with existing synthetic card identities. The wide report camera stays inside the phone frame; mobile/landscape camera keeps its viewport controls. Actual application local records (wine-demo-saved-v1) must be preserved by the application session; the mockup's in-memory Set is NOT a storage migration.
8. Exact home heading: 'Какое вино перед вами?'. Same wording in the specimen and tokens.
9. Home uses one opaque warm canvas (`#fbf6ec`) from the logo through the mascot scene. The disconnected `Поиск по этикетке` descriptor is removed from the logo row. The home brand row is not a capsule and has no blur, border, or visual seam. This rule applies only to home; context bars on other screens are unchanged.

## Canonical design sources

- site/design.js: rendered product screens and components, lower navigation, catalog/Saved and error states.
- site/flow-state.js: canonical prototype navigation/request simulation. app.js no longer contains competing transition functions.
- site/navigation-v2.js: report-only screen/scenario picker. Never carry this report shell into the app.
- site/app.js: report scenarios, explanations and references.
- site/migration-ux.css: final overrides for navigation, state notes and desktop phone frame. Final cascade is style.css -> design.css -> mascot-preview.css -> v2.css -> brand-map.css -> review-v2.css -> mascot-scenes.css -> migration-ux.css. Do not take the first matching legacy rule as the target value.
- site/tokens.json: core material tokens, title and bottom navigation contract.
- The selected home art now uses the transparent local asset `site/assets/v2/mascot-hold-2d-alpha.png`; generation provenance and visual checks are recorded in `mascot-scenes.md`. Other selected local 2D assets are unchanged.

The mock camera/gallery, two synthetic wines keyed by year, substring search and 1200ms response are prototype mechanics only. They are not approved implementations or real API data. The application should preserve its actual File/receipt, candidate ID, catalog, storage and server error contracts.

## Acceptance checks

### Issue #24: no-match screenshot follow-up

Maks's red annotations were found by sigma-ops in Hermes Telegram context, linked to [issue #24](https://github.com/ai-babai/brutforce/issues/24), but were not copied into that issue originally. The old PR #25 concerns proposal inventory, not these UI changes. Current design owner: sigma - front; implementation handoff: sigma-ops-server-ops-bdd.

- Candidate list is the uncertain recognition outcome when usable candidates exist. True no-match does not fabricate similar wines, ratings or probabilities. No new intermediate screen is introduced.
- Photo no-match: primary `Найти по названию`, secondary `Переснять этикетку`. Both are full-width, centered, 56 px minimum, 16 px radius and 10 px gap. The first uses the existing wine fill, the second the existing outlined style.
- Manual no-match: primary `Изменить запрос`, returns to the same editable query. Do not display an unrelated retained scan on this text-only failure.
- Copy does not infer a missing catalog record or poor image quality from no-match alone.
- New static 2D art `site/assets/v2/mascot-counter-thoughtful-2d.png`: neutral concerned mouth/eyebrows, same counter, pose, hat, scarf and magnifying glass. Previous art remains in Git. The mascot stays behind the action panel and never overlaps labels.
- Built-in imagegen edit prompt: change only facial expression; remove smile, slightly concerned mouth corners/raised inner eyebrows; attentive, no tears or dramatic sadness; preserve 3:2 composition, muted watercolor style and light background. Original reference: `mascot-counter-2d.png`.
- `tests/migration.cjs` UX-M10 covers aligned actions at 320/390, no fabricated candidates, manual miss -> editable retained query, no unrelated photo. Existing flows cover ambiguous -> candidates -> manual, preview and reshoot.
- Application handoff: update existing UI-022 so the Home item asserts navigation to the start screen and never opens the camera. Add a separate assertion that the large scan CTA opens the camera. Keep Search and Saved checks unchanged.

This handoff updates mockups only. BDD session should adapt actual recognition candidates, file context and query state, then run its application checks. No report publication is included in this change.

Run tests/flows.cjs and tests/migration.cjs with the documented Playwright runtime. UX-M01..10 verify cancel/delete/resume identity, success/error arriving behind preview, query/list/scroll return, original versus newly selected identity, distinct error states, reshoot, catalog/Saved save/delete, Home/Search/Saved navigation, explicit camera entry, wide frame, exact heading and the simplified home logo row. Existing flow checks remain and include the new report states. Parent and independent GPT-5.6 browser review cover visual geometry; tests do not claim physical-device or real camera/network validation.

## Follow-up: alpha across every selected mascot scene

Maks approved the same treatment for all illustrations. Use `-2d-alpha.png` variants for hold (home), walk (loading/waiting), cellar (empty manual search), counter-thoughtful (no match), offline (network unavailable). Keep scene objects and opaque whites; remove the baked rectangular paper backdrop. Preserve alpha in app WebP exports. See tokens.json and mascot-scenes.md. This is an asset correction, not a new user step or state.
