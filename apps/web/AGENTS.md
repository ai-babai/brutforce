# Web demo area

This directory owns the runnable React behavior demo. It consumes the JSON search API and never presents simulated recognition as a measured model result.

- Keep stable journey screen IDs `UI-001` through `UI-010` when changing markup.
- Uploaded images stay in browser memory for preview. The current API request sends only `scenario` and optional `query`.
- Preserve the atlas wine palette, local Onest font, and first-party concept bottle. Do not add competitor screenshots.
- Verify behavior with `npm test` and the production bundle with `npm run build`.
