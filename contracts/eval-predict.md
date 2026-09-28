# Contest prediction endpoint

**Status:** implemented HTTP boundary. The executable configures a real
recognizer when `VISION_SERVICE_URL` is set; otherwise it returns 503.

**Producer:** `apps/api` Go server. **Consumer:** the organizer's local
`participant_test.sh`. This is separate from the synthetic demo search
contract and from private demo-photo storage.

## Request

`POST /v1/eval/predict` accepts `multipart/form-data` with exactly one file
part named `image`. The filename and declared part MIME type are not trusted.
The server reads at most 10 MiB, recognizes JPEG, PNG, GIF, and WebP from the
decoder, then checks a maximum 12,000-pixel side and 25,000,000 pixels before
fully decoding the image. The image is held only for the request and is never
written to `UPLOAD_DIR` or exposed through an HTTP route.

The request context has a nine-second deadline from handler entry. A recognizer
must stop its own work when that context is cancelled; the HTTP boundary does
not claim to safely terminate a recognizer that ignores its context.

`EVAL_MAX_CONCURRENT` sets the number of simultaneous decode-and-recognize
requests; it defaults to 4 and invalid values use that default. This cap is
independent of the demo's search/upload rate budgets, so sequential organizer
requests are not rejected by the demo's low burst limit.

## Response

On a successful recognizer result, the response is HTTP 200 with the exact
nonempty slug returned by the recognizer and verified against the pinned
organizer slug allowlist:

```json
{"slug":"catalog-slug"}
```

The standalone boundary does not normalize or invent a slug. The configured
vision adapter checks it against the organizer catalog allowlist. A test stub proves
only the HTTP hand-off; it is not evidence of recognition quality.

A deliberate `no_match` or `insufficient_information` response is HTTP 200
with `{"slug":"","action":"..."}`. This is an explicit abstention, not a
catalog prediction. The organizer script requires a nonempty slug and records
both cases as null; retain response status and action in our own diagnostics
to distinguish them from a technical failure, which returns an error status.

Errors are JSON objects with an `error.code` and `error.message`. Invalid
multipart/image input is HTTP 400; a wrong method is 405; no configured
recognizer is the honest HTTP 503 `recognition_unavailable`; concurrency is
429; a context timeout is 504. The organizer client records any non-200/201
response as no prediction and continues.

## Wiring boundary

The application creates the endpoint with a nil `Recognizer` unless
`VISION_SERVICE_URL` is set. The configured adapter consumes the shared
ranked serving contract in [vision-serving.md](vision-serving.md). An injected
engine implements:

```go
type Recognizer interface {
    Recognize(context.Context, image.Image) (string, error)
}
```

Injected recognizers receive a fully decoded bounded image and must respect
the supplied context. The configured HTTP adapter additionally implements
`EncodedRecognizer`, so it forwards the validated original bytes to the
serving process without encoding the decoded image again. The model and index
run in that separate process; the Go adapter pins their response versions and
the organizer slug allowlist.

## Behavior checks

| ID | Given / When | Then |
|---|---|---|
| EVAL-001 | Stub recognizer returns a slug | HTTP 200 returns that exact slug |
| EVAL-002 | Synthetic WebP bytes arrive with a `.jpg` name | Decoder accepts it by content |
| EVAL-003 | Missing, duplicate, extra, or invalid multipart input | HTTP 400 |
| EVAL-004 | Wrong method or unknown `/v1/eval/...` route | JSON 405 or 404 |
| EVAL-005 | Valid image and no configured recognizer | JSON 503 `recognition_unavailable`, never a slug |
| EVAL-006 | Caller cancels while recognizing | Recognizer receives cancellation and response is 408 |
| EVAL-007 | Truncated, oversized, or oversized-dimension image | HTTP 400 before recognition |
| EVAL-008 | Repeated valid requests with `UPLOAD_DIR` configured | All succeed without demo rate limiting or saved files |
| EVAL-009 | Recognition slot is occupied | A second request gets 429 and the slot releases afterward |

Run only this boundary's fast suite with:

```sh
cd apps/api
go test -count=1 -run '^TestEVAL' ./...
```
