package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"image"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type realVisionCatalog struct{ items []wine }

func (c realVisionCatalog) List(context.Context) ([]wine, error) { return c.items, nil }
func (c realVisionCatalog) Search(_ context.Context, query *string) ([]wine, error) {
	if query == nil {
		return c.items, nil
	}
	for _, item := range c.items {
		if strings.Contains(strings.ToLower(item.Name), strings.ToLower(*query)) {
			return []wine{item}, nil
		}
	}
	return []wine{}, nil
}
func (c realVisionCatalog) CatalogInfo(context.Context) (catalogInfo, error) {
	return catalogInfo{Version: "catalog-display-v2", Demo: false}, nil
}
func (c realVisionCatalog) Resolve(_ context.Context, slug string) (wine, string, error) {
	for _, item := range c.items {
		if item.Slug == slug {
			return item, item.ID, nil
		}
	}
	return wine{}, "", errCatalogNotFound
}

func TestVISION001ContestAndAppUseSameRealRanking(t *testing.T) {
	photo := smallPNG(t)
	const first = "real-catalog-slug-a"
	const second = "real-catalog-slug-b"
	catalog := realVisionCatalog{[]wine{{ID: "database-id-a", Slug: first, Name: "Wine A"}, {ID: "database-id-b", Slug: second, Name: "Wine B"}}}
	requests := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		if r.URL.String() != "/v1/eval/predict?track=service" {
			t.Errorf("unexpected URL %s", r.URL)
		}
		if err := r.ParseMultipartForm(11 << 20); err != nil {
			t.Error(err)
			return
		}
		file, _, err := r.FormFile("image")
		if err != nil {
			t.Error(err)
			return
		}
		buf := new(bytes.Buffer)
		_, _ = buf.ReadFrom(file)
		if !bytes.Equal(buf.Bytes(), photo) {
			t.Error("upstream received altered image bytes")
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		_ = json.NewEncoder(w).Encode(visionResult{Slug: first, RankedSlugs: []string{first, second}, CatalogVersion: "organizer-catalog-20260919", IndexVersion: "index-v1", ModelVersion: "model-v1"})
	}))
	defer upstream.Close()
	client := &visionClient{baseURL: upstream.URL, catalogVersion: "organizer-catalog-20260919", indexVersion: "index-v1", client: noRedirectHTTPClient(), validSlugs: map[string]struct{}{first: {}, second: {}}}
	storeDir := t.TempDir()
	store, err := openPhotoStore(storeDir, 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := store.save(photo, "image/png", image.Config{Width: 2, Height: 3})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Setenv("UPLOAD_DIR", storeDir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Unsetenv("UPLOAD_DIR") })
	t.Setenv("FEEDBACK_DIR", t.TempDir())
	h := newHandlerWithCatalogAndServices("", nil, catalog, modelServices{vision: client})
	eval := evalImageRequest(t, h, "image", "label.png", photo, nil)
	if eval.Code != 200 || !strings.Contains(eval.Body.String(), `"slug":"`+first+`"`) {
		t.Fatalf("eval: %d %s", eval.Code, eval.Body.String())
	}
	search := request(t, h, http.MethodPost, "/v1/search", `{"photoId":"`+receipt.ID+`"}`)
	if search.Code != 200 {
		t.Fatalf("search: %d %s", search.Code, search.Body.String())
	}
	var result searchResponse
	if err := json.Unmarshal(search.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if result.Demo || result.CatalogVersion != "catalog-display-v2" || result.SelectedID != "" || len(result.Candidates) != 2 || result.Candidates[0].ID != "database-id-a" || result.Candidates[1].ID != "database-id-b" || len(result.FeedbackToken) != 32 || requests != 2 {
		t.Fatalf("result=%+v requests=%d", result, requests)
	}
}

func TestVISIONTopFiveEvalUsesOneOrganizerRanking(t *testing.T) {
	mode := "match"
	requests := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		w.Header().Set("Content-Type", "application/json")
		result := visionResult{CatalogVersion: "organizer-v1", IndexVersion: "index-v1", ModelVersion: "model-v1"}
		if mode == "match" {
			result.Slug = "organizer-only"
			result.RankedSlugs = []string{"organizer-only", "second", "third", "fourth", "fifth", "sixth"}
		} else {
			result.Action = "no_match"
			result.RankedSlugs = []string{}
		}
		_ = json.NewEncoder(w).Encode(result)
	}))
	defer upstream.Close()
	client := &visionClient{baseURL: upstream.URL, catalogVersion: "organizer-v1", indexVersion: "index-v1", client: noRedirectHTTPClient(), validSlugs: map[string]struct{}{"organizer-only": {}, "second": {}, "third": {}, "fourth": {}, "fifth": {}, "sixth": {}}}
	h := newEvalPredictHandler(&visionRecognizer{client: client}, 1)
	call := func(query string) *httptest.ResponseRecorder {
		t.Helper()
		req := evalMultipartRequest(t, "image", "photo.png", smallPNG(t), nil)
		req.URL.RawQuery = query
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		return w
	}
	w := call("")
	if w.Code != 200 || w.Body.String() != "{\"slug\":\"organizer-only\"}\n" || requests != 1 {
		t.Fatalf("default: status=%d body=%s requests=%d", w.Code, w.Body.String(), requests)
	}
	w = call("top_k=5")
	if w.Code != 200 || w.Body.String() != "{\"slug\":\"organizer-only\",\"ranked_slugs\":[\"organizer-only\",\"second\",\"third\",\"fourth\",\"fifth\"]}\n" || requests != 2 {
		t.Fatalf("top5: status=%d body=%s requests=%d", w.Code, w.Body.String(), requests)
	}
	for _, query := range []string{"top_k=0", "top_k=6", "top_k=5&top_k=5", "top_k="} {
		w = call(query)
		if w.Code != 400 || requests != 2 {
			t.Fatalf("invalid %s: status=%d body=%s requests=%d", query, w.Code, w.Body.String(), requests)
		}
	}
	mode = "no_match"
	w = call("top_k=5")
	if w.Code != 200 || w.Body.String() != "{\"action\":\"no_match\",\"ranked_slugs\":[]}\n" || requests != 3 {
		t.Fatalf("no match: status=%d body=%s requests=%d", w.Code, w.Body.String(), requests)
	}
}

func TestVISION002AbstentionAndUnknownSlugStayDistinct(t *testing.T) {
	catalog := realVisionCatalog{[]wine{{ID: "id-a", Slug: "known", Name: "Known"}}}
	mode := "no_match"
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		out := visionResult{CatalogVersion: "organizer-catalog-20260919", IndexVersion: "index-v1", ModelVersion: "model-v1", RankedSlugs: []string{}}
		if mode == "bad" {
			out.Slug, out.RankedSlugs = "unknown", []string{"unknown"}
		} else if mode == "organizer-only" {
			out.Slug, out.RankedSlugs = "organizer-only", []string{"organizer-only"}
		} else {
			out.Action = mode
		}
		_ = json.NewEncoder(w).Encode(out)
	}))
	defer upstream.Close()
	client := &visionClient{baseURL: upstream.URL, client: noRedirectHTTPClient(), validSlugs: map[string]struct{}{"known": {}, "organizer-only": {}}}
	h := newHandlerWithCatalogAndServices("", nil, catalog, modelServices{vision: client})
	noMatch := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
	if noMatch.Code != 200 || !strings.Contains(noMatch.Body.String(), `"action":"no_match"`) {
		t.Fatalf("no match: %d %s", noMatch.Code, noMatch.Body.String())
	}
	mode = "organizer-only"
	outside := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
	if outside.Code != 200 || !strings.Contains(outside.Body.String(), `"slug":"organizer-only"`) {
		t.Fatalf("valid organizer-only slug: %d %s", outside.Code, outside.Body.String())
	}
	photo := smallPNG(t)
	dir := t.TempDir()
	store, err := openPhotoStore(dir, 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := store.save(photo, "image/png", image.Config{Width: 2, Height: 3})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Setenv("UPLOAD_DIR", dir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Unsetenv("UPLOAD_DIR") })
	h = newHandlerWithCatalogAndServices("", nil, catalog, modelServices{vision: client})
	mode = "no_match"
	noMatchSearch := request(t, h, http.MethodPost, "/v1/search", `{"photoId":"`+receipt.ID+`"}`)
	var noMatchResult searchResponse
	if err := json.Unmarshal(noMatchSearch.Body.Bytes(), &noMatchResult); err != nil {
		t.Fatal(err)
	}
	if noMatchSearch.Code != http.StatusOK ||
		noMatchResult.Action != "no_match" ||
		noMatchResult.RecognizedSlug != "" ||
		noMatchResult.SelectedID != "" ||
		len(noMatchResult.Candidates) != 0 {
		t.Fatalf("app no match response: %d %+v", noMatchSearch.Code, noMatchResult)
	}

	mode = "organizer-only"
	search := request(t, h, http.MethodPost, "/v1/search", `{"photoId":"`+receipt.ID+`"}`)
	var result searchResponse
	if err := json.Unmarshal(search.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if search.Code != 200 || result.Action != "outside_display_catalog" || result.RecognizedSlug != "organizer-only" || len(result.Candidates) != 0 {
		t.Fatalf("outside display response: %d %+v", search.Code, result)
	}
	mode = "bad"
	unknown := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
	if unknown.Code != 502 || !strings.Contains(unknown.Body.String(), "recognition_invalid_result") {
		t.Fatalf("unknown: %d %s", unknown.Code, unknown.Body.String())
	}
}

func TestVISION003PinnedOrganizerAllowlist(t *testing.T) {
	data := []byte(`{"catalog_version":"organizer-catalog-20260919","slugs":["known","organizer-only"]}`)
	path := filepath.Join(t.TempDir(), "slugs.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(data)
	known, err := loadVisionSlugs(path, hex.EncodeToString(sum[:]), "organizer-catalog-20260919")
	if err != nil || len(known) != 2 {
		t.Fatalf("known=%v err=%v", known, err)
	}
	if _, err := loadVisionSlugs(path, strings.Repeat("0", 64), "organizer-catalog-20260919"); err == nil {
		t.Fatal("mismatched hash accepted")
	}
	if _, err := loadVisionSlugs(path, hex.EncodeToString(sum[:]), "other-catalog"); err == nil {
		t.Fatal("mismatched version accepted")
	}
}

type officialAliasVisionCatalog struct {
	realVisionCatalog
	aliases map[string]string
}

func (c officialAliasVisionCatalog) CatalogInfo(context.Context) (catalogInfo, error) {
	return catalogInfo{Version: "svoe-20260922-v2", Demo: false}, nil
}

func (c officialAliasVisionCatalog) Resolve(ctx context.Context, slug string) (wine, string, error) {
	if canonical, ok := c.aliases[slug]; ok {
		item, _, err := c.realVisionCatalog.Resolve(ctx, canonical)
		return item, canonical, err
	}
	return wine{}, "", errCatalogNotFound
}

func TestVISION004OnlyPinnedOfficialAliasMapsToCanonicalCard(t *testing.T) {
	const alias = "aligote-avtorskoe"
	const canonical = "aligote-avtorskoe-vino"
	const unofficial = "some-other-organizer-slug"
	catalog := officialAliasVisionCatalog{
		realVisionCatalog: realVisionCatalog{items: []wine{{ID: "database-canonical-id", Slug: canonical, Name: "Алиготе"}}},
		aliases:           map[string]string{alias: canonical, unofficial: canonical},
	}
	top := alias
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(visionResult{Slug: top, RankedSlugs: []string{top, canonical}, CatalogVersion: "organizer-catalog-20260919", IndexVersion: "index-v1", ModelVersion: "model-v1"})
	}))
	defer upstream.Close()
	client := &visionClient{baseURL: upstream.URL, catalogVersion: "organizer-catalog-20260919", indexVersion: "index-v1", client: noRedirectHTTPClient(), validSlugs: map[string]struct{}{alias: {}, canonical: {}, unofficial: {}}}
	store, err := openPhotoStore(t.TempDir(), 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	photo := smallPNG(t)
	receipt, err := store.save(photo, "image/png", image.Config{Width: 2, Height: 3})
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/v1/search", nil)
	result, status, _, _ := configuredVisionSearch(request, store, catalog, receipt.ID, client)
	if status != 0 || result.Action != "" || result.RecognizedSlug != alias || len(result.Candidates) != 1 || result.Candidates[0].ID != "database-canonical-id" || result.Candidates[0].Slug != canonical || result.SelectedID != "" {
		t.Fatalf("official alias: status=%d result=%+v", status, result)
	}
	top = unofficial
	result, status, _, _ = configuredVisionSearch(request, store, catalog, receipt.ID, client)
	if status != 0 || result.Action != "outside_display_catalog" || result.RecognizedSlug != unofficial || len(result.Candidates) != 0 {
		t.Fatalf("unofficial alias: status=%d result=%+v", status, result)
	}
}

func TestVISION005AppUsesLongCeilingAndParentDeadlineWins(t *testing.T) {
	if visionRequestDeadline != 18*time.Second {
		t.Fatalf("vision deadline=%v, want 18s", visionRequestDeadline)
	}
	if serverWriteTimeout != 30*time.Second || visionRequestDeadline >= serverWriteTimeout {
		t.Fatalf("write timeout=%v must leave margin after vision deadline=%v", serverWriteTimeout, visionRequestDeadline)
	}
	const slug = "known"
	validResponse := `{"slug":"known","ranked_slugs":["known"],"catalog_version":"organizer-v1","index_version":"index-v1","model_version":"model-v1"}`
	remaining := make(chan time.Duration, 2)
	transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		deadline, ok := r.Context().Deadline()
		if !ok {
			t.Error("vision request has no deadline")
		}
		remaining <- time.Until(deadline)
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(validResponse)),
		}, nil
	})
	client := &visionClient{
		baseURL:        "http://vision.invalid",
		catalogVersion: "organizer-v1",
		indexVersion:   "index-v1",
		client:         &http.Client{Transport: transport},
		validSlugs:     map[string]struct{}{slug: {}},
	}
	store, err := openPhotoStore(t.TempDir(), 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	photo := smallPNG(t)
	receipt, err := store.save(photo, "image/png", image.Config{Width: 2, Height: 3})
	if err != nil {
		t.Fatal(err)
	}
	catalog := realVisionCatalog{items: []wine{{ID: "id-known", Slug: slug, Name: "Known"}}}
	request := httptest.NewRequest(http.MethodPost, "/v1/search", nil)
	result, status, _, _ := configuredVisionSearch(request, store, catalog, receipt.ID, client)
	if status != 0 || len(result.Candidates) != 1 || result.Candidates[0].ID != "id-known" {
		t.Fatalf("app search: status=%d result=%+v", status, result)
	}
	appRemaining := <-remaining
	if appRemaining < visionRequestDeadline-time.Second || appRemaining > visionRequestDeadline {
		t.Fatalf("app vision deadline remaining=%v, want long ceiling up to %v", appRemaining, visionRequestDeadline)
	}

	parent, cancel := context.WithTimeout(context.Background(), evalRecognitionDeadline)
	defer cancel()
	if _, err := client.predict(parent, photo); err != nil {
		t.Fatal(err)
	}
	evalRemaining := <-remaining
	if evalRemaining <= 0 || evalRemaining > evalRecognitionDeadline {
		t.Fatalf("parent deadline remaining=%v, want at most %v", evalRemaining, evalRecognitionDeadline)
	}
}

func TestVISION006UnknownReceiptAndCorruptStorageStayDistinct(t *testing.T) {
	store, err := openPhotoStore(t.TempDir(), 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, "/v1/search", nil)
	catalog := realVisionCatalog{items: []wine{{ID: "id-known", Slug: "known", Name: "Known"}}}
	client := &visionClient{}

	_, status, code, _ := configuredVisionSearch(request, store, catalog, "0123456789abcdef0123456789abcdef", client)
	if status != http.StatusNotFound || code != "photo_not_found" {
		t.Fatalf("unknown receipt: status=%d code=%s", status, code)
	}

	photo := smallPNG(t)
	receipt, err := store.save(photo, "image/png", image.Config{Width: 2, Height: 3})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(store.originalPath(receipt.ID), []byte("truncated"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, status, code, _ = configuredVisionSearch(request, store, catalog, receipt.ID, client)
	if status != http.StatusServiceUnavailable || code != "storage_unavailable" {
		t.Fatalf("corrupt original: status=%d code=%s", status, code)
	}
}
