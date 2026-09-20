# Wine UX 2.0

Initiator: Maks, 2026-09-20. Static design system and clickable wine label scanner prototype. A separate version, based on the local Atlas at b1fac93. No application/API implementation.

Inputs: prior Atlas flows and Q&A interpretation, public Svoye Vino CSS/screenshots in mascot-lab research, user-selected refined 2D dog holding a bottle. Outputs: references, component system, flow explorer, decisions, sources, and collapsed changelog.

Canonical code: site/. Public target: https://reps.maks.dzap.pw/v2/#flows. Prior /view and /mascots are preserved. All assets are local; no backend, camera, or recognition service is invoked.

Review scope: all scenario paths, cancel/retry, gallery, manual query, result tabs, candidate choice, camera viewport, touch controls, image loading, reduced transparency, narrow report layout. Temporary checks only under /tmp, per root instructions.

Brand values are observed in public CSS. Their adaptation, spacing and use of the mascot are design decisions, not official brand approval. Dates/limitations of inherited research remain attached to its sources.

## Navigation and brand integration correction — 2026-09-20

Independent GPT-5.6 browser review identified sticky-navigation occlusion, undiscoverable mobile tabs, scenario entry ambiguity, and duplicated progress markers. The report now exposes 15 distinct screen choices (the catalog state shares the result view), immediately shows each scenario's characteristic outcome, and retains a separate start-to-finish action. Mobile selectors and wrapped section navigation replace hidden horizontal choices. Steps are clickable and one current step is highlighted; component links retain a matching scenario.

The component section includes six source/adaptation comparisons with locally preserved source screenshots, explicit CSS-only provenance for the floating search, and links to actual screens. Product screens apply warm navigation capsules, milk search/status layers, opaque cream candidates/facts and bottle-first result hierarchy. Old reports are unchanged.

Validation: Chrome at 320/390/1440, all 16 render states, 10 scenario outcomes, recovery and manual search; separate actual-click review by GPT-5.6. This remains a static prototype.

Secondary 2D mascot integration: see [composition, prompts and verification](mascot-scenes.md). Static scenes on loading/waiting, missing result and empty manual search; selected home artwork unchanged.

Current selected edition: [scope, transition decisions and immutable archive](selected-edition.md). Design-specific persistent acceptance checks were explicitly requested by Maks; see [tests](tests/README.md). The pre-selection frame experiment is preserved at `/v2/previous/` rather than used in the current flow.

Approved migration handoff (b73baf6 plan): [decisions, files and acceptance cases](migration-handoff.md). These later source changes are Git-only until a static-report release; published-version.json remains the deployed version's record.
