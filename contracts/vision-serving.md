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
`VISION_INDEX_VERSION` to pin expected upstream data versions. A mismatch,
malformed response, duplicate rank, or slug absent from the active real
PostgreSQL catalog fails closed. This mapping uses catalog `slug` to resolve
the application's distinct `id`; it never constructs a card from model text.

Contest prediction returns only the first verified slug. A deliberate
abstention returns HTTP 200 with its action and no slug, which the organizer
script records as null. Upstream transport/validation/catalog failures return
non-200 errors, not a successful abstention. The original organizer script
must receive an explicit endpoint because its default port may belong to
another service on Sigma.

For app photo search, the same ranking is mapped to up to five existing card
IDs in order. The response has no `selectedId`: rank is not calibrated
confidence. Real-catalog text search uses the local catalog search. The
recommendation service remains a separate wine-ID operation and never feeds
contest prediction or recognition candidates.
