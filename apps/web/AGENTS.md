# Web demo area

This directory owns the runnable React behavior demo. It consumes the JSON search API and never presents simulated recognition as a measured model result.

- Keep stable journey screen IDs `UI-001` through `UI-010` when changing markup.
- Photos upload to private server storage via /v1/photos; search uses the photoId receipt at /v1/search. See contracts/photo-upload.md.
- PWA is optional. Keep the same journey available in ordinary tabs; never gate camera/search on installation. No offline promise or service worker cache. Test browser and standalone modes, short viewport and safe areas.
- Use the selected Wine UX v2 design and approved migration plan (`../../docs/product/design-v2-migration-plan.md`): local Onest font, selected first-party mascot scenes and wine palette. Keep concept bottle only for catalog fixtures where it is an actual synthetic image; never invent a user photo. Do not add competitor screenshots or prototype report controls.
- Verify behavior with `npm test` and the production bundle with `npm run build`.
