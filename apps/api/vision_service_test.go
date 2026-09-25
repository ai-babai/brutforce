package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"image"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
	if result.Demo || result.CatalogVersion != "catalog-display-v2" || result.SelectedID != "" || len(result.Candidates) != 2 || result.Candidates[0].ID != "database-id-a" || result.Candidates[1].ID != "database-id-b" || requests != 2 {
		t.Fatalf("result=%+v requests=%d", result, requests)
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
