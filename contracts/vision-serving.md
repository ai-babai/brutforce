# Shared vision serving boundary

The Go API uses one ranked image result for both `POST /v1/eval/predict` and
photo `POST /v1/search`. Configure `VISION_SERVICE_URL` as an internal HTTP(S)
origin. Its serving process accepts `POST /v1/eval/predict?track=service` with
one multipart file field named `image` and returns JSON. The Go boundary sends
the validated original bytes, with an 8.5-second upstream deadline inside its
nine-second request budget. It does not send a stored photo path or public URL.

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
IDs in order. If its top slug has no display card, the response is empty with
`action: outside_display_catalog`, `recognizedSlug`, and both catalog
versions; the UI explains that the card is unavailable. Missing later slots
are omitted and marked `partial_display_catalog`, without promoting a lower
rank to an exact match. The response has no `selectedId`: rank is not calibrated
confidence. Real-catalog text search uses the local catalog search. The
recommendation service remains a separate wine-ID operation and never feeds
contest prediction or recognition candidates.

The 2026-09-25 TEST audit found 2,103 organizer slugs and 2,038 display
slugs, with 2,034 shared, 69 organizer-only, and four display-only. These
figures describe the pinned TEST versions, not a rule for future catalogs.
