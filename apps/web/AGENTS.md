# Web demo area

This directory owns the runnable React behavior demo. It consumes the JSON search API and never presents simulated recognition as a measured model result.

- Keep stable journey screen IDs `UI-001` through `UI-010` when changing markup.
- Photos upload to private server storage via /v1/photos; search uses the photoId receipt at /v1/search. See contracts/photo-upload.md.
- PWA is optional. Keep the same journey available in ordinary tabs; never gate camera/search on installation. No offline promise or service worker cache. Test browser and standalone modes, short viewport and safe areas.
- Preserve the atlas wine palette, local Onest font, and first-party concept bottle. Do not add competitor screenshots.
- Verify behavior with `npm test` and the production bundle with `npm run build`.
