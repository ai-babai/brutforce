# Selected mascot edition of design 2.0

Initiator: Maks. Session 01a0aa4a-9655-7c12-8c1e-fe02a7fcc299. Static prototype only. User explicitly authorized design-specific scenarios and persistent acceptance tests.

Accepted mascot scenes: home; search/loading and extended wait (walk among bottles/barrels); no match (counter); manual search before results (shelf); connection failure (new phone/crate illustration). The frame/cancelled-screen experiment is not included in this edition. No mascot on native gallery, permission instructions, camera, photograph inspection or wine comparison/data.

The new offline asset `site/assets/v2/mascot-offline-2d.png` was generated with built-in image_gen from the selected 2D dog. Prompt: same flat gouache beagle detective, tan checked cap/coat, burgundy scarf; calmly checks a raised smartphone beside a crate with two bottles; patient expression, no warning symbol/text/UI, warm #FEFDFA and feathered edges. The actual retained user photo stays separate and clickable. No offline recognition promise.

## Navigation decisions

- Cancel -> home with last-photo resume/preview controls; pending timer stopped. No separate cancelled page or confirmation.
- Preview -> exact originating state, including offline or home. Inspecting during retry preserves the retry outcome.
- Manual search -> candidate -> wine -> back to original query/candidate. Failed query remains editable; no user photo fabricated.
- Wrong wine -> candidates or manual search; candidates return to the originating result when reached through correction.
- Bad-frame reshoot can succeed in the demo, rather than looping forever in the same failure.
- Gallery and permissions remain minimal simulations, not mascot-bearing proprietary substitutes for native UI.

## Preserved previous edition

Public URL: /v2/previous/. Immutable source commit: 922709f (metadata 7543d05). Server release: /srv/lct/maks/wine-ux-v2/releases/v2-20260920-922709f. Each new current release must contain `previous -> ../v2-20260920-922709f` before switching the current symlink. The archive's original files are not rewritten. Git preserves the source without copying assets into a second source directory.

Original /view and /mascots are unchanged. New selected edition remains /v2/.

## Validation

See tests/README.md. Parent runs persisted click-path checks plus visual inspection. Independent GPT-5.6 review checked cancellation/resume, offline/preview/retry and manual hit/miss/back behavior at mobile width; no blocking issue or dead end found. Real camera/network/recognition and physical devices remain outside scope.
