# Mascot composition research: character as interface layer

## What the correction changes

The mascot should not consume a dedicated icon slot beside otherwise empty content. In the strongest real screens it does one of four jobs: it *is the setting*, it enters from an edge, it anchors a state transition, or it becomes the reward/result. The surrounding controls sit in the negative space created by its silhouette.

## 1. Finch — home/goal scene (official live UI shown in App Store)

Reference: `finch-appstore-2.jpg`; official listing: https://apps.apple.com/us/app/finch-self-care-pet/id1528595748

- **Position and share:** two birbs stand in the upper/middle scene and take a visibly substantial part of the illustrated scene above the task sheet. Any numeric share would be an eyeballed estimate, so it should not be treated as a layout specification.
- **Layering:** characters and trees are one spatial world. The white goal panel overlaps the lower edge of that world rather than placing a character in a row beside text.
- **UI relationship:** checking goals affects the pet/adventure. The mascot is therefore a visible consequence of the list, not a label for the list.
- **State:** companion/adventure state on the same screen as the actionable checklist.
- **Transfer to wine:** on search/waiting, make the character occupy the search environment (shelf/cellar/table), with the results sheet sliding over or under it. The character can inspect a label or lean toward the bottle crop. Do not reserve a left column.

## 2. Finch — persistent widget (real user screenshot)

Reference: `finch-user-widget.jpeg`; post: https://www.reddit.com/r/finch/comments/1gnox59/finchie_widget/

- **Position and share:** character is centered and full-body; it is large enough to read outfit and expression, while the room/background fills the entire tile. The useful meter floats at the bottom and overlaps the scene.
- **Layering:** the mascot is embedded in a personalized room; furniture frames it and makes the whole tile feel inhabited.
- **Action:** passive presence, customized outfit, visible energy progress. No speech bubble is required.
- **User response:** author says seeing the birb prevents forgetting to check in; commenters call it calming/encouraging and say the widget sold them on the app and increases opens. A request for animation appears, countered by battery concerns—good evidence to keep the first wine implementation static.
- **Transfer to wine:** the scan entry/return card can be a small diorama: the pet beside the last recognized bottle, recent search or cellar shelf, with the progress/status pill overlaid at the bottom.

## 3. Study Bunny — timer + paused state (official actual UI)

References: `study_bunny-appstore-1.png`, `study_bunny-appstore-6.png`; official listing: https://apps.apple.com/us/app/study-bunny-focus-timer/id1478345385

- **Position and share:** on the normal timer, the full bunny sits prominently in the bottom third of the scenic background. On the paused screen, its ears/head enter from the bottom beneath a large speech bubble. These are visual relationships, not measured ratios.
- **Layering:** scenery runs edge to edge under the controls. Timer, controls, book/music shortcuts and coins float above it. The bunny is not inside a card.
- **Action/state:** normal state is “studying with you”; paused state changes pose and presents a relevant motivational line. The same character signals system status without an extra icon.
- **Transfer to wine:** for recognition, use one stage with pose changes: looking through bottle labels while processing; presenting the chosen bottle when matched; peeking up with an empty tray when no match. Keep buttons/pills as overlays in clear sky/wall/table negative space.

## 4. Duolingo — lesson-complete result panel (real user screenshot)

Reference: `duolingo-user-lesson-complete.jpg`; post: https://www.reddit.com/r/duolingo/comments/1i2r3wm/whats_your_favourite_lesson_complete_screen/

- **Position and share:** the character variant dominates the captured panel and is centered above the single visible outcome line. The source is a partial user capture, so it does not establish the geometry of the whole screen.
- **Layering:** within the visible panel there is no card, avatar frame or icon slot. Character, shadow and dark field form a single poster-like result composition. The outcome line sits in the lower negative space. No controls are visible in the capture.
- **Action/state:** completion reward imagery; the static capture confirms the strong silhouette and absurd pose, but does not show the animation or subsequent action.
- **User response:** mixed by design. Some call the excited screens cute and the unicorn wholesome/amazing; others call variants disturbing, over the top and want a disable option. This is a useful boundary: large is effective, but shock/absurdity can overpower a utilitarian task.
- **Transfer to wine:** reserve a dominant result illustration for decisive moments (first successful scan, rare find, saved favorite), not every result. Use a calmer “reveal” pose with bottle/result information immediately below.

## 5. Headspace — character as landscape (official actual UI)

Reference: `headspace-appstore-4.png`; official listing: https://apps.apple.com/us/app/headspace-sleep-meditation/id493145008

- **Position and share:** the orange face spans essentially the full hero width. Only eyes/mouth are needed; the character's body becomes the hill/horizon. The proportion is observed from this screenshot, not offered as a universal target.
- **Layering:** course title, duration, teacher choice and CTA remain in the clean white lower area. The mascot does not compete with controls because its silhouette creates a simple top field.
- **Action/state:** ambient emotional framing (“calm”) rather than instruction or navigation.
- **Transfer to wine:** turn the mascot into a cropped background shape on onboarding/empty state—e.g. body as a burgundy cellar arch or tasting-table foreground, face/eyes directed toward the bottle capture area. A crop can feel larger and more integrated than a full-body figure.

## 6. Khan Academy Kids — characters inhabit the learning surface (official UI composite)

Reference: `khan_kids-appstore-1.jpg`; official listing: https://apps.apple.com/us/app/khan-academy-kids/id1378467217

- **Position and share:** characters appear around and inside the activity canvas; outside characters act as foreground guides while the exercise remains central. Their combined silhouette is visually substantial without requiring a dedicated UI column.
- **Layering:** characters overlap the edge of the activity device/canvas and stand on the same ground plane, connecting decoration to the task.
- **Transfer to wine:** on guided camera setup, let the character partially enter from below/side and point toward the actual scan frame. Its gaze and gesture should explain where to place the label; instructional text can stay short.

## Rules for the next static wine screens

1. **No mascot slot.** Do not add a new grid column or leading avatar. Character pixels must overlap a background, edge, hero, result object or card boundary.
2. **Size from the job and silhouette.** Make the character large enough for its gaze, pose or prop to read; allow a more dominant composition for a short reward/result state. The references do not support one universal percentage range.
3. **One spatial relationship per screen.** The character looks at, holds, reveals, searches for, or sits beside the bottle/result. Generic waving wastes the integration.
4. **Let silhouette create layout.** Put copy and controls in the negative space beside/above the pose, or place a bottom sheet over the scene.
5. **Crop intentionally.** A face/horizon or body entering from an edge often feels more native than a small full-body sticker.
6. **Static first.** Encode state with pose, gaze, prop and composition. Later animation should be brief and state-triggered; avoid permanent motion on search/result screens.

## Four concrete wine adaptations to prototype

- **Camera guidance:** large character enters from the lower-right, body cropped by the viewport, holding a bottle so its label aligns with the scan frame. Instruction occupies clear upper-left space.
- **Recognition/searching:** full-bleed cellar/shelf scene; character is physically comparing 2–3 labels. A compact progress/status pill overlays the bottom of the scene.
- **Match result:** bottle remains the primary object; character pulls back a curtain/leaf or presents the bottle from behind it. Product data begins in an overlapping bottom sheet.
- **No match/weak photo:** character peeks over an empty tasting tray or blurred label crop. Retry controls sit in the tray/table negative space; no sad avatar beside an error paragraph.

## Caveat on evidence

The two Reddit files are direct user screenshots with visible community reaction. App Store files are official screenshots of the product UI, sometimes placed inside marketing framing; analysis above refers only to the UI visible inside the phone/screen, not to decorative headline copy around it.
