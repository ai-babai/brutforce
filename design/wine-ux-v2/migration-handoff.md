# Approved migration UX - design handoff

2026-09-20. Initiator: Maks, delegated from session 01a0b128-3ad8-72e1-ad67-4ade90613061 to design session 01a0aa4a-9655-7c12-8c1e-fe02a7fcc299. Based on docs/product/design-v2-migration-plan.md, b73baf6 in codex/behavior-demo. This change edits static design only. No apps/web/API/storage code was changed. Publication metadata continues to describe the previously deployed edition until an explicit static-report release.

## Accepted decisions and examples

1. Cancel an active photo search -> Scanner/home, retained-photo controls: Continue search / View photo / Delete photo. No automatic restart. Delete invalidates any pending simulated response and removes the retained-photo actions. Resume reuses the current mock photo ID; another capture obtains a new one.
2. Photo preview retains the origin and does not stop the request. If the request finishes while preview is open, the preview remains open with a short status. Closing shows the fresh result/error, not stale loading and not a second request. If still pending, it returns to the same pending search.
3. Manual search keeps the query, result list and inner/page scroll when returning from a card. Empty search has a short hint and explicit catalog access. Catalog opens the same candidate component; missing text results keep the query editable. Text-only paths never synthesize a user photo.
4. The explicit 'Not this wine' action captures the original identity/year, detail tab, return target and whether the photo relates to that result. Candidate/manual detours can return to that exact card. A newly selected wine remains separate from the original correction context; choosing it does not overwrite the correction origin. Normal Back to candidates is not reinterpreted as a new correction action. Saved/catalog/text-only cards go directly to manual search on correction; unrelated candidates from a retained scan are never shown. Empty manual search places its input before the hint/catalog entry and mascot.
5. offline = network unavailable; servererror = service response failed; missing = no suitable match. Only the first two offer retry of the retained photo. An unknown match is not evidence of a server failure or poor image quality.
6. unreadable = image file cannot be opened, never sent to search in this demo. badphoto = explicit trustworthy quality signal that the label is unreadable; no assumed glare cause. missing = no match with unknown cause. Each has a different explanation and recovery. New valid file/reshoot can leave an error state.
7. Preserve Scanner / Search / Saved bottom navigation. Hide on camera. Save/remove is demonstrated with existing synthetic card identities. The wide report camera stays inside the phone frame; mobile/landscape camera keeps its viewport controls. Actual application local records (wine-demo-saved-v1) must be preserved by the application session; the mockup's in-memory Set is NOT a storage migration.
8. Exact home heading: 'Какое вино перед вами?'. Same wording in the specimen and tokens.

## Canonical design sources

- site/design.js: rendered product screens and components, lower navigation, catalog/Saved and error states.
- site/flow-state.js: canonical prototype navigation/request simulation. app.js no longer contains competing transition functions.
- site/navigation-v2.js: report-only screen/scenario picker. Never carry this report shell into the app.
- site/app.js: report scenarios, explanations and references.
- site/migration-ux.css: final overrides for navigation, state notes and desktop phone frame. Final cascade is style.css -> design.css -> mascot-preview.css -> v2.css -> brand-map.css -> review-v2.css -> mascot-scenes.css -> migration-ux.css. Do not take the first matching legacy rule as the target value.
- site/tokens.json: core material tokens, title and bottom navigation contract.
- Existing selected local 2D assets are unchanged.

The mock camera/gallery, two synthetic wines keyed by year, substring search and 1200ms response are prototype mechanics only. They are not approved implementations or real API data. The application should preserve its actual File/receipt, candidate ID, catalog, storage and server error contracts.

## Acceptance checks

Run tests/flows.cjs and tests/migration.cjs with the documented Playwright runtime. UX-M01..08 verify cancel/delete/resume identity, success/error arriving behind preview, query/list/scroll return, original versus newly selected identity, distinct error states, reshoot, catalog/Saved save/delete, bottom navigation, camera and wide frame, exact heading. Existing flow checks remain and include the new report states. Parent and independent GPT-5.6 browser review cover visual geometry; tests do not claim physical-device or real camera/network validation.
