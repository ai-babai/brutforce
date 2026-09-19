# Duolingo mascot UI screen references — visually inspected

Research date: 2026-09-19. The four downloaded files in `/tmp/duo-v4/` were opened at original resolution and inspected. Labels below distinguish provenance; none is called an official in-app screenshot unless the source supports that.

## Best transferable examples

### 1. Start-lesson loading screen — real app screenshot, third-party flow archive

- Original page: https://www.lazyweb.com/flow/duolingo/start-lesson
- Direct asset: https://zlfyzdmohcskkucuunmk.supabase.co/storage/v1/object/public/screenshots/uploaded_duolingo/compare/2026-02-20/1771692126944_F669D391-31AE-416A-98DB-D6CC1DA97BC1_1_105_c.jpeg
- Local: `/tmp/duo-v4/loading.jpeg` (602 × 1308)
- Classification: real product screenshot archived by Lazyweb; not an official Duolingo promo. The file's EXIF says `Screenshot` and `2026:02:20 13:02:48`; this is asset metadata, not independently verified release dating.
- Observed composition: near-black full-screen field; small white Duolingo wordmark centered in the system-bar zone; a compact Duo vignette near mid-screen, sitting on three books and reading a blue book; muted `LOADING...` directly beneath; a two-line fact/question below in brighter white. Most of the screen is empty, so the mascot reads as a calm focal point rather than a large hero. No button is present.
- Safe transfer to wine-search dog detective: place the dog in one self-contained activity vignette (reading a tasting notebook, examining a label, or holding a loupe) above a quiet progress word, followed by one short wine-search fact or status. For our wine-search adaptation keep cancellation available; the absence of controls in this source is not a recommendation. Use generous negative space and one bright character accent against a dark field. Do not copy Duo, the books, wording, colors, or proportions exactly.

### 2. Widget mood progression — official Duolingo promotional/design image

- Original page: https://blog.duolingo.com/widget-feature/
- Direct asset: https://storage.ghost.io/c/7a/33/7a33d0f4-927d-4fe8-a6bf-96131b5e76d4/content/images/2023/08/widgets.png
- Local: `/tmp/duo-v4/widgets.png` (1196 × 786)
- Classification: official Duolingo blog asset presenting widget variants; promotional composite, not a phone screenshot.
- Observed composition: fourteen compact rounded-square widgets in three rows on a dark presentation field. Each tile reserves its top band for the flame/streak number and a tiny imperative, while Duo occupies or breaks into the lower area. The unfinished-day sequence moves from vivid lime to purple, blue, green, orange/red, and magenta as poses progress from inviting to tired, sick, angry, and tearful. Completed states switch to pale backgrounds and relaxed celebratory poses. Several variants crop Duo at the bottom or sides, so the frame feels like a physical window that the mascot presses against or rises through.
- Safe transfer: make one fixed widget grammar—small status at top, detective dog entering from the lower or side edge—and change only pose, crop, expression, prop, and background according to search state. For example: nose and eyes peeking while idle; head plus loupe while searching; a calm neutral expression for no results; relaxed dog with bottle silhouette after a find. The useful idea is stateful framing and escalation, not Duolingo's guilt language or palette.

### 3. Generic failure alert over loading art — counterexample only; user/shared screenshot, version unverified

- Aggregated source page: https://x.com/i/trending/1856886095553970319
- Direct asset: https://pbs.twimg.com/media/GcS98gkWwAAYzm5.jpg
- Local: `/tmp/duo-v4/error.jpg` (554 × 1200)
- Classification: user/shared mobile screenshot surfaced by X image search. The exact author post, app build, and date were not recoverable from the aggregate page; treat version/date as unverified. It should not be described as an official designed error example.
- Observed composition: dark iPhone screen at 22:53. The same reading-on-books Duo vignette sits behind a native dark alert. Only the character's upper head, eyes, book, and a sliver of books remain visible above the dialog; this is occlusion by a system alert, not a bespoke edge-peek illustration. The alert contains the title `Something went wrong!`, two-line recovery/support copy, and one blue `OK` action. Dimmed mission copy remains visible behind it.
- Design lesson: this is not evidence of a successful integrated mascot error state. The native alert accidentally obscures the loading vignette and leaves a distracting fragment of Duo visible. For the wine app, either dim/cover the background cleanly or design a bespoke error card with an intentional dog silhouette and identifying prop. Do not reproduce this collision and do not cite it as an intentional peek pattern.

### 4. Lesson-complete screen — reproduced product screenshot in design press

- Original page: https://page-online.de/kreation/wie-duolingo-mit-illustrationen-das-lernen-neu-erfindet/
- Direct asset: https://page-online.de/app/uploads/2023/08/Duolingo_Screenshot_lesson-863x1536.png
- Local: `/tmp/duo-v4/lesson-complete.png` (863 × 1536)
- Classification: Duolingo product screenshot reproduced by PAGE magazine; not hosted by Duolingo and appears to show an older UI. It is neither fan art nor a redesign mockup.
- Observed composition: white full-height rounded device frame. Large yellow `Lesson complete!` anchors the top; sparse firework marks sit in corners. A character pair occupies the central stage, standing on a light baseline. Duo is small and deadpan beside a much larger human character, which creates comic contrast. Below are two wide outlined reward rows with labels left and yellow lightning/value right. A saturated blue full-width `CONTINUE` button closes the screen at the bottom.
- Safe transfer: we reject a separate celebration for every wine match: a learning milestone differs from obtaining a search result. Keep wine identity and source primary.

## What these examples support

- Mascot placement works as a state layer: centered activity for waiting, framed/cropped entrance for persistent widgets, accidental occlusion behind a system alert (counterexample), and a broad stage for success.
- The character does not need to be huge. Recognition comes from silhouette, eyes/expression, and one state-specific prop.
- Text hierarchy stays simple: one status phrase, at most one short supporting thought, and one primary action when action is possible.
- Edge peeking is strongest when the container behaves like a physical aperture. The official widget sheet is stronger evidence for this than the failure screenshot, whose crop is accidental alert occlusion.
- For the wine-search dog, use investigation behavior rather than generic cheerleading: sniffing a trail, loupe to label, notebook, cork clue, ear/eyebrow changes. This transfers the interaction role without copying Duolingo's owl personality.

## Exclusions and caveats

- Search results included a Figma clone (`x.com/LTofeik/...`) and UX bootcamp launch-screen reproductions. They were excluded because they are recreations or secondary captures and add no safer pattern beyond the verified references above.
- The BHirst loading image is a third-party animation still and older light-theme example. The Lazyweb capture is more useful because its source presents a dated, step-by-step in-market flow and the downloaded file is a full screenshot.
- No dimensions, spacing values, color hex values, animation timing, or implementation metrics are inferred from these images.
- The X error asset has weak post-level provenance. Use it only as visual evidence of an encountered state, with the qualification above.
