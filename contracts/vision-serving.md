# Shared vision serving boundary

The Go API uses one ranked image result for both `POST /v1/eval/predict` and
photo `POST /v1/search`. Configure `VISION_SERVICE_URL` as an internal HTTP(S)
origin. Its serving process accepts `POST /v1/eval/predict?track=service` with
one multipart file field named `image` and returns JSON. The Go boundary sends
the validated original bytes with an 18-second upstream ceiling. The app route
uses that ceiling inside the HTTP server's 30-second write timeout; the separate
20-second read timeout still bounds the incoming request body. The complete
app `/v1/search` route has a 25-second processing budget, leaving time around
the vision call for receipt verification, catalog mapping, and JSON. Contest
prediction supplies its shorter nine-second parent deadline, which remains
authoritative. It does not send a stored photo path or public URL.

An unknown private photo receipt returns `404 photo_not_found`. If receipt
metadata exists but its original is missing, corrupt, unreadable, or has an
unexpected size, app search returns `503 storage_unavailable`; storage damage
must not masquerade as an unknown user receipt.

The vision response requires `catalog_version`, `index_version`,
`model_version`, and `ranked_slugs` (ordered, at most 20 exact organizer slugs).
For a recognized target, `slug` equals `ranked_slugs[0]`. For a deliberate
abstention, the rank list is empty, `slug` is absent, and `action` is
`no_match` or `insufficient_information`. Additional diagnostic fields are
ignored by the Go consumer. Configure `VISION_CATALOG_VERSION` and
`VISION_INDEX_VERSION` to pin expected upstream data versions. The runtime
also requires a private, versioned organizer slug allowlist at
`VISION_SLUGS_FILE` and its SHA-256 at `VISION_SLUGS_SHA256`. A mismatch,
malformed response, duplicate rank, or slug outside that pinned organizer
allowlist fails closed. The app separately maps each displayed slug to its
distinct PostgreSQL `id`; it never constructs a card from model text.

Contest prediction returns only the first organizer-verified slug. It does
not require a display card: the competition catalog and the app's imported
display catalog have different versions and coverage. A deliberate
abstention returns HTTP 200 with its action and no slug, which the organizer
script records as null. Upstream transport/validation/catalog failures return
non-200 errors, not a successful abstention. The original organizer script
must receive an explicit endpoint because its default port may belong to
another service on Sigma.

For app photo search, the same ranking is mapped to up to five existing card
IDs in order. In display version `svoe-20260922-v2`, three pinned official
aliases may resolve to their canonical cards only when the catalog resolver
confirms the exact mapping; the response keeps the original organizer slug in
`recognizedSlug` and deduplicates canonical IDs. Other organizer-only slugs
remain unavailable without a documented mapping. If its top slug has no display card, the response is empty with
`action: outside_display_catalog`, `recognizedSlug`, and both catalog
versions; the UI explains that the card is unavailable. Missing later slots
are omitted and marked `partial_display_catalog`, without promoting a lower
rank to an exact match. The response has no `selectedId`: rank is not calibrated
confidence. Real-catalog text search uses the real display catalog even when
the demo reference service is configured; `query` takes priority over
`photoId`. Without vision, real-catalog photo search returns 503 rather than
synthetic results.

Real-catalog `POST /v1/recommendations` uses an offline visual-neighbor map
from the same pinned SO400M reference index as F8, not the ranked candidates
from an individual recognition request. `RECOMMENDATION_INDEX_FILE` must match
`RECOMMENDATION_INDEX_SHA256`; the catalog version must match the active display
catalog, and the index version must match vision at startup. It returns
distinct other display cards by exact ID. This is visual label similarity,
not tasting or personalized recommendations. Missing source vectors yield an
empty candidate list. Demo retains its independent recommendation service.

The 2026-09-25 TEST audit found 2,103 organizer slugs and 2,038 display
slugs, with 2,034 shared, 69 organizer-only, and four display-only. These
figures describe the pinned TEST versions, not a rule for future catalogs.
