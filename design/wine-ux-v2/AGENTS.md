# Wine UX 2.0

Standalone static design system and clickable report. Start with README.md.

- User explicitly requested version 2.0, preserving the prior Atlas and mascot studies.
- Canonical v2 files live in site/. Do not edit design/wine-ux-atlas or design/mascot-lab for v2 changes.
- This is a prototype, not camera/recognition implementation. Preserve demo labels and source attribution.
- Use refined 2D bottle-in-paws art. Glass is for navigation/context; data and key actions have stable opaque surfaces.
- Keep the same report structure, scenarios, recovery paths and collapsed changelog.
- Publish only this site's contents at /v2/; old /view and /mascots stay unchanged.
- Prefer GPT-5.6 for bounded implementation work. Parent visually verifies all screens before delivery.
- Selected mascot edition: follow selected-edition.md. No separate cancelled screen; cancel returns home with retained-photo actions. Preserve /v2/previous/ as immutable release 922709f on every deployment.
- User explicitly authorized design-specific persistent tests under tests/. They do not cover real recognition/camera.
- Approved migration handoff: migration-handoff.md. Preserve Scanner/Search/Saved, exact home heading, request completion behind preview, correction identity and manual search position. Canonical prototype transitions: site/flow-state.js.
