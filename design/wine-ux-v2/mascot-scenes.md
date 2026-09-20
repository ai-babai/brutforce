# Secondary mascot scenes - 2026-09-20

Initiator: Maks. Scope: incremental static v2 mockup update. Home remains unchanged. Session 01a0aa4a-9655-7c12-8c1e-fe02a7fcc299, branch codex/camera-viewport, FE-023.

Three new images were generated with the built-in image_gen tool from the selected 2D bottle-in-paws character. Original generated PNGs are preserved in site/assets/v2. No 3D artwork is reused in the new interface.

- mascot-walk-2d.png: loading and waiting, walking between wine racks and barrels; user explicitly recalled this earlier composition. Input 1: selected 2D character; input 2: old mascot-lab/site/assets/journey/cellar.png as composition-only reference. No notebook, gaze toward bottles.
- mascot-counter-2d.png: missing result, upper body emerges behind a counter immediately above recovery actions. It provides reassurance without celebrating failure.
- mascot-cellar-2d.png: manual search before results, inspecting labels on a rack. Removed when a candidate appears.

Composition follows prior research in mascot-lab/research/other-screens-v4.md: bounded scene adjacent to state (Finch), partial character above/below a panel (Study Bunny), search among objects. These are our adaptations, not claims these wine screens exist in the reference products. Existing source/provenance limitations remain applicable.

Input photo remains a separate, legible control. Preview returns to the originating state; returning to transient loading restarts its demo transition. No mascot on camera, photo comparison, candidates, result data or technical permission/network errors. All new scenes are static; no timing/accuracy claims.

## Prompt set

Common identity: the selected reference's flat 2D gouache beagle detective, ochre ears, cream muzzle, tan checked cap and coat, muted wine-red scarf, fine brown outlines and softly textured shading; never 3D. Wide 3:2 illustration for a mobile wine scanner; calm desaturated cream/tan/burgundy, outer background #FEFDFA, no text/UI/frame.

Cellar: actively inspect labels on a low two-tier wooden wine rack through a magnifying glass. Dog on right, bottles across lower half, no notebook, no elaborate scenery, generous margins, complete hat and paws. A purposeful scene rather than an icon.

Counter: upper body peeks from behind a thin wooden counter at bottom. Both paws rest over its edge, one holds a lowered magnifying glass. Thoughtful reassuring expression, slight head tilt, not sad or celebrating. Body hidden by counter, no bottle, no icons, no baked UI card. Scene adjoins the actual actions panel.

Walk: use old cellar image only for walking action/composition; preserve the selected flat 2D style. Full-body beagle mid-stride in cellar aisle, looking at wine labels, carrying lowered magnifier; no paper/notebook. Low rack at left, oak barrels and bottles at right, complete central silhouette. Restrained ground joins objects, scene dissolves into warm ivory, readable at 350x220. Still image, no animation.

## Verification

Temporary browser QA: 16 states at 320/390, 10 scenario paths and recovery actions. Independent GPT-5.6 click/visual review of all four changed states at 320/390/1440: photo preview/back, cancellation/retry, manual search removing the scene when a candidate appears. No content/control overlaps or horizontal overflow. Parent inspected rendered mobile screens. Real recognition, camera and physical devices remain outside this static prototype.
