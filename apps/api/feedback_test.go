package main

import (
	"bytes"
	"context"
	"encoding/json"
	"image"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

type feedbackTestCatalog struct{ items []wine }

func (catalog feedbackTestCatalog) List(context.Context) ([]wine, error) {
	return append([]wine(nil), catalog.items...), nil
}
func (catalog feedbackTestCatalog) Search(context.Context, *string) ([]wine, error) {
	return append([]wine(nil), catalog.items...), nil
}

func feedbackFixture(t *testing.T) (*feedbackStore, *photoStore, string, string) {
	t.Helper()
	photos, err := openPhotoStore(filepath.Join(t.TempDir(), "photos"), 1<<20, 10000)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := photos.save([]byte("private-photo-bytes"), "image/jpeg", image.Config{Width: 10, Height: 10})
	if err != nil {
		t.Fatal(err)
	}
	feedback, err := openFeedbackStore(filepath.Join(t.TempDir(), "feedback"))
	if err != nil {
		t.Fatal(err)
	}
	response := searchResponse{
		Demo: true, Candidates: demoWines[:2], SelectedID: demoWines[0].ID,
		CatalogVersion: defaultCatalogVersion, ModelVersion: "test-model-v1",
	}
	token, err := feedback.createSession(photos, receipt.ID, "request-test", response)
	if err != nil {
		t.Fatal(err)
	}
	return feedback, photos, token, receipt.ID
}

func postFeedback(t *testing.T, handler http.Handler, body feedbackRequest) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/v1/feedback", bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func TestFeedbackConfirmIsAppendOnlyAndIdempotent(t *testing.T) {
	feedback, photos, token, photoID := feedbackFixture(t)
	handler := feedbackHandler(feedback, photos, embeddedCatalogStore{})
	request := feedbackRequest{
		FeedbackToken: token, IdempotencyKey: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Decision: "confirm", DisplayedWineID: demoWines[0].ID, Comment: "Верный редизайн",
	}
	first := postFeedback(t, handler, request)
	if first.Code != http.StatusCreated {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	reopened, err := openFeedbackStore(feedback.dir)
	if err != nil {
		t.Fatal(err)
	}
	second := postFeedback(t, feedbackHandler(reopened, photos, embeddedCatalogStore{}), request)
	if second.Code != http.StatusOK {
		t.Fatalf("retry status=%d body=%s", second.Code, second.Body.String())
	}
	files, err := os.ReadDir(filepath.Join(feedback.dir, "records"))
	if err != nil || len(files) != 1 {
		t.Fatalf("records=%d err=%v", len(files), err)
	}
	data, err := os.ReadFile(filepath.Join(feedback.dir, "records", files[0].Name()))
	if err != nil {
		t.Fatal(err)
	}
	var record feedbackRecord
	if err := json.Unmarshal(data, &record); err != nil {
		t.Fatal(err)
	}
	if record.PhotoID != photoID || record.Decision != "confirm" || record.TrainingEligible || record.ReviewStatus != "pending_review" || record.OriginalSelectedID != demoWines[0].ID {
		t.Fatalf("unexpected record: %+v", record)
	}
}

func TestFeedbackCorrectRequiresDifferentCatalogWineAndProtectsIdempotency(t *testing.T) {
	feedback, photos, token, _ := feedbackFixture(t)
	handler := feedbackHandler(feedback, photos, embeddedCatalogStore{})
	request := feedbackRequest{
		FeedbackToken: token, IdempotencyKey: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		Decision: "correct", DisplayedWineID: demoWines[0].ID, CorrectWineID: demoWines[1].ID,
	}
	created := postFeedback(t, handler, request)
	if created.Code != http.StatusCreated {
		t.Fatalf("created status=%d body=%s", created.Code, created.Body.String())
	}
	request.Comment = "different payload"
	conflict := postFeedback(t, handler, request)
	if conflict.Code != http.StatusConflict {
		t.Fatalf("conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	request.IdempotencyKey = "cccccccccccccccccccccccccccccccc"
	request.CorrectWineID = request.DisplayedWineID
	invalid := postFeedback(t, handler, request)
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("same wine correction status=%d body=%s", invalid.Code, invalid.Body.String())
	}
}

func TestFeedbackResolvesCatalogIdentityByIDNotSlug(t *testing.T) {
	feedback, photos, token, _ := feedbackFixture(t)
	items := append([]wine(nil), demoWines[:2]...)
	items[0].ID, items[0].Slug = demoWines[0].ID, "slug-distinct-from-internal-id"
	handler := feedbackHandler(feedback, photos, feedbackTestCatalog{items: items})
	response := postFeedback(t, handler, feedbackRequest{
		FeedbackToken: token, IdempotencyKey: "dddddddddddddddddddddddddddddddd",
		Decision: "confirm", DisplayedWineID: items[0].ID,
	})
	if response.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	data, err := os.ReadFile(filepath.Join(feedback.dir, "records", "dddddddddddddddddddddddddddddddd.json"))
	if err != nil {
		t.Fatal(err)
	}
	var record feedbackRecord
	if err := json.Unmarshal(data, &record); err != nil {
		t.Fatal(err)
	}
	if record.TargetCanonicalID != items[0].ID || record.TargetSlug != items[0].Slug {
		t.Fatalf("identity mismatch: id=%q slug=%q", record.TargetCanonicalID, record.TargetSlug)
	}
}

func TestFeedbackRecordsCorrectWineAfterModelNoMatch(t *testing.T) {
	feedback, photos, _, photoID := feedbackFixture(t)
	token, err := feedback.createSession(photos, photoID, "request-no-match", searchResponse{
		Demo: true, CatalogVersion: defaultCatalogVersion, ModelVersion: "test-model-v1",
	})
	if err != nil {
		t.Fatal(err)
	}
	response := postFeedback(t, feedbackHandler(feedback, photos, embeddedCatalogStore{}), feedbackRequest{
		FeedbackToken: token, IdempotencyKey: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		Decision: "correct", CorrectWineID: demoWines[1].ID,
	})
	if response.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	data, err := os.ReadFile(filepath.Join(feedback.dir, "records", "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.json"))
	if err != nil {
		t.Fatal(err)
	}
	var record feedbackRecord
	if err := json.Unmarshal(data, &record); err != nil {
		t.Fatal(err)
	}
	if record.OriginalOutcome != "no_match" || record.DisplayedWineID != "" || record.DisplayOrigin != "model_no_match" || record.TargetCanonicalID != demoWines[1].ID {
		t.Fatalf("unexpected no-match record: %+v", record)
	}
}

func TestFeedbackRetrySurvivesMissingPhotoAndCatalogChange(t *testing.T) {
	feedback, photos, token, photoID := feedbackFixture(t)
	request := feedbackRequest{
		FeedbackToken: token, IdempotencyKey: "ffffffffffffffffffffffffffffffff",
		Decision: "confirm", DisplayedWineID: demoWines[0].ID,
	}
	handler := feedbackHandler(feedback, photos, embeddedCatalogStore{})
	if first := postFeedback(t, handler, request); first.Code != http.StatusCreated {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}
	if err := os.Remove(filepath.Join(photos.dir, photoID+".bin")); err != nil {
		t.Fatal(err)
	}
	changedCatalog := feedbackTestCatalog{items: []wine{{ID: "unrelated", Slug: "changed"}}}
	if retry := postFeedback(t, feedbackHandler(feedback, photos, changedCatalog), request); retry.Code != http.StatusOK {
		t.Fatalf("retry status=%d body=%s", retry.Code, retry.Body.String())
	}
}
