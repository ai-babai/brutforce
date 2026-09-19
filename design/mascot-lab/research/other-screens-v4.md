# Mascot UI composition references for the wine-search dog detective

Checked 2026-09-19. The three App Store examples below are **publisher-supplied promotional screenshots**, not independent user captures. They contain legible in-app UI, but the headline/background framing may be composed for the store. The Khan Academy Kids example is an **actual app screen reproduced in the publisher's official help center**. No claim below depends on inferred animation or interaction.

## 1. Finch — character scene immediately above the task/results stack

- **Visible layout:** Two finches occupy a compact illustrated city scene in the top half of the phone. A white status strip (`Adventuring`, progress dots, return time) touches the scene's lower edge. A green count row (`3 goals left today!`) and white task cards continue directly beneath it. The pet scene, progress summary, and actionable list read as one vertical story.
- **Useful pattern:** Put the dog detective in a shallow “investigation stage” immediately above the search-status counter and results. The dog can walk/sniff in that bounded stage during loading; the same stable strip below can say a truthful indeterminate search status and then become a real result summary (never fabricated counts) without moving the results origin.
- **Limitation:** This is an App Store promo image supplied by Finch. It demonstrates hierarchy and adjacency, but it does not prove every current production state or transition. It shows pets *above* a counter/list rather than peeking from behind it.
- **Source page:** https://apps.apple.com/us/app/finch-self-care-pet/id1528595748
- **Direct asset:** https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/01/f7/19/01f7194f-379f-5b81-bb5d-e05a30711938/iPhone_social_large_04.jpg/320x480bb.jpg
- **Saved copy:** `/tmp/other-v4/01-finch-adventure-and-goals.jpg`

## 2. Study Bunny — mascot rises from below a dominant state panel

- **Visible layout:** The paused screen is mostly a calm green field. `Paused`, a short explanation, timer, and a large speech bubble form a centered stack. At the bottom edge, only the upper part of the bespectacled bunny and a sleeping companion are visible; the characters are deliberately cropped by the viewport, as if entering from below.
- **Useful pattern:** A strong loading/no-result composition: keep the search copy and one actionable button centered, then let the dog's ears, nose, or magnifying glass rise from the lower edge. The crop creates presence without competing with the state message. On no results, the speech bubble could hold the useful next step (`Попробуйте название или другое фото`) while the dog remains a supporting actor.
- **Limitation:** Publisher-supplied App Store promotional screenshot. The crop is real in the pictured UI, but the surrounding headline is store artwork. It is a pause state, not a search empty state.
- **Source page:** https://apps.apple.com/us/app/study-bunny-focus-timer/id1478345385
- **Direct asset:** https://is1-ssl.mzstatic.com/image/thumb/Purple122/v4/38/71/f1/3871f167-1266-caf6-20bc-5f81e9c53cd2/pr_source.png/392x696bb.png
- **Saved copy:** `/tmp/other-v4/02-study-bunny-paused.png`

## 3. Readmio — mascot overlaps the browse panel from the outside

- **Visible layout:** A large white `Browse` panel contains the search field, editor picks, age groups, and categories. A pink elephant stands outside/right of that panel and overlaps its edge, covering a small portion of the content area while keeping labels readable. The elephant is layered over the promotional browse-panel composition; whether it appears in the live app is not established.
- **Useful pattern:** This is the closest reference for a dog “searching among shelves.” Build the wine filters/results as the primary white surface, then place the detective on its outside edge, partially occluded by the panel or leaning around it. During loading, the dog's nose/magnifier can cross the boundary into a shelf row; in results, reduce it to a small edge peek so cards remain primary.
- **Limitation:** Publisher-supplied App Store promo, and the mascot appears as a static illustration in store artwork over a browse screen; in-product placement is unverified. It does not demonstrate live search behavior. The character overlaps content enough that the same treatment would need a reserved gutter on narrow phones.
- **Source page:** https://apps.apple.com/us/app/readmio-kids-books-read-aloud/id1473021827
- **Direct asset:** https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/6f/b4/b7/6fb4b750-9c9d-6f6f-9597-95e0040f5b20/Screenshot_3.png/320x480bb.jpg
- **Saved copy:** `/tmp/other-v4/03-readmio-browse.jpg`

## 4. Khan Academy Kids — cast below one oversized “start” object

- **Visible layout:** The home screen centers a whimsical house and an oversized circular play button. Five mascots form a low horizontal row beneath the house, with their bodies cropped by the bottom edge. Small utility controls stay in the corners/top bar, leaving one unmistakable primary action.
- **Useful pattern:** For the wine-search home, treat the search field/button as the “house”: a single oversized investigation entry point, with the detective dog positioned below it rather than inside the control. The dog's placement can establish personality before any query. When a search begins, the same character can move into the Finch-style stage above status/results, giving the mascot a coherent spatial journey.
- **Limitation:** This is a real app screen from an official help article, but it is a children's learning home screen on a tablet-sized canvas. Five characters and a giant play target are too theatrical for a wine tool; borrow the central-anchor + low mascot silhouette, not the density or scale.
- **Source page:** https://khankids.zendesk.com/hc/en-us/articles/360048828572-Learn-more-about-the-Learning-Path
- **Direct asset:** https://khankids.zendesk.com/hc/article_attachments/360067963091
- **Saved copy:** `/tmp/other-v4/04-khan-kids-learning-path.png`

## Recommended four-state sequence

| Wine-search state | Composition to borrow | Guardrail |
|---|---|---|
| Home | Khan Kids: one large central search action, dog grounded below it | Keep one dog, not an ensemble; search must still look like an input, not a game button |
| Loading | Finch: shallow scene immediately above a persistent progress/count strip | Cap the scene height so content does not jump when results arrive |
| No result | Study Bunny: centered explanation/action with dog cropped at bottom | Dog should reinforce the message; remediation copy and button stay first |
| Results | Readmio: dog peeks around/behind the results surface, pointing attention inward | Reserve an edge gutter and prevent overlap with prices, labels, or tap targets |

The coherent motif is **boundary crossing**: the dog begins below the search control, enters a small investigation scene while searching, peeks up beneath the no-result message, and finally leans around the results panel. This gives the mascot a job in each state without turning every screen into a full illustration.

## Provenance / local files

Apple metadata used to resolve publisher pages and current screenshot URLs was fetched from the public iTunes Search/Lookup API. Copies are unmodified downloads at the sizes served by the URLs above.

| File | SHA-256 |
|---|---|
| `01-finch-adventure-and-goals.jpg` | `43f3197baa783ee6c8b32ef9bf6c73aec2d7de8b492fe3828c8d7a8a3266204a` |
| `02-study-bunny-paused.png` | `05abc7f2bd2b58272eb84b882d799012776b4e9bd5ebe1fb1ead759ecc6b808c` |
| `03-readmio-browse.jpg` | `16b4d4dbb37fb1724ad38829050af2432d4f47da319098df008298fcc71ec83c` |
| `04-khan-kids-learning-path.png` | `fb4820f0cfc5c3ca7564171196f2faad01c4cfee2d9160489a4353fce7973eec` |
