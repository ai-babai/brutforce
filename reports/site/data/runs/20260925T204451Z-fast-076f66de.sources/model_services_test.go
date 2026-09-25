package main

import (
	"context"
	"encoding/json"
	"errors"
	"image"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"brutforce-behavior-demo/apps/api/internal/referenceengine"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestSVC001ConfiguredTextSearchEnrichesProviderOrder(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path != "/v1/search/text" || r.Header.Get("X-Request-ID") != "safe-42" {
			t.Fatalf("unexpected upstream request %s id=%q", r.URL.Path, r.Header.Get("X-Request-ID"))
		}
		var input struct {
			CatalogVersion string `json:"catalogVersion"`
			Limit          int    `json:"limit"`
		}
		if err := json.NewDecoder(r.Body).Decode(&input); err != nil || input.CatalogVersion != "demo-v1" || input.Limit != 5 {
			t.Fatal("bad upstream JSON")
		}
		_ = json.NewEncoder(w).Encode(modelResponse{CatalogVersion: "demo-v1", ModelVersion: "roman-1", Demo: false, Candidates: []modelCandidate{{ID: demoWines[1].ID, Score: .9}, {ID: demoWines[0].ID, Score: .9}}, SelectedID: demoWines[1].ID})
	}))
	defer upstream.Close()
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}})
	r := httptest.NewRequest(http.MethodPost, "/v1/search", strings.NewReader(`{"scenario":"error","query":"merlot"}`))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-Request-ID", "safe-42")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, r)
	response := decodeResponse(t, rec)
	if rec.Code != 200 || !response.Demo || response.ModelVersion != "roman-1" || response.SelectedID != demoWines[1].ID || len(response.Candidates) != 2 || response.Candidates[0].ID != demoWines[1].ID {
		t.Fatalf("response=%d %+v", rec.Code, response)
	}
}

func TestSVC002ConfiguredServicesRejectInvalidProviderData(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(modelResponse{CatalogVersion: "wrong", ModelVersion: "m", Demo: false, Candidates: []modelCandidate{{ID: "unknown", Score: .9}}})
	}))
	defer upstream.Close()
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}})
	rec := request(t, h, http.MethodPost, "/v1/search", `{"query":"x"}`)
	if rec.Code != http.StatusBadGateway {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestSVC003RecommendationsUseSeparateServiceAndRejectSource(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path != "/v1/recommendations" {
			t.Fatal(r.URL.Path)
		}
		_ = json.NewEncoder(w).Encode(modelResponse{CatalogVersion: "demo-v1", ModelVersion: "rec-1", Demo: true, Candidates: []modelCandidate{{ID: demoWines[2].ID, Score: .8}}})
	}))
	defer upstream.Close()
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{recommendations: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}})
	rec := request(t, h, http.MethodPost, "/v1/recommendations", `{"wineId":"demo-cabernet-sauvignon-2023","limit":1}`)
	result := decodeResponse(t, rec)
	if rec.Code != 200 || result.ModelVersion != "rec-1" || len(result.Candidates) != 1 {
		t.Fatalf("%d %+v", rec.Code, result)
	}
	noService := request(t, newHandler(""), http.MethodPost, "/v1/recommendations", `{"wineId":"demo-cabernet-sauvignon-2023"}`)
	if noService.Code != http.StatusServiceUnavailable {
		t.Fatal(noService.Code)
	}
}

func TestSVC004ReferenceEngineHTTPContract(t *testing.T) {
	server := httptest.NewServer(referenceengine.Handler())
	defer server.Close()
	response, err := http.Post(server.URL+"/v1/search/text", "application/json", strings.NewReader(`{"query":"x","catalogVersion":"demo-v1","limit":2}`))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	var result referenceengine.Response
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	if !result.Demo || referenceengine.ValidateResponse(result, "demo-v1", "", true) != nil {
		t.Fatalf("%+v", result)
	}
}

func TestSVC005PhotoSearchForwardsPrivateBytes(t *testing.T) {
	dir := t.TempDir()
	store, err := openPhotoStore(dir, 20<<20, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	receipt, err := store.save([]byte("private-photo"), "image/png", image.Config{Width: 1, Height: 1})
	if err != nil {
		t.Fatal(err)
	}
	_ = os.Setenv("UPLOAD_DIR", dir)
	t.Cleanup(func() { _ = os.Unsetenv("UPLOAD_DIR") })
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path != "/v1/search/image" {
			t.Fatal(r.URL.Path)
		}
		if err := r.ParseMultipartForm(11 << 20); err != nil {
			t.Fatal(err)
		}
		file, _, err := r.FormFile("image")
		if err != nil {
			t.Fatal(err)
		}
		data, _ := io.ReadAll(file)
		if string(data) != "private-photo" {
			t.Fatal("photo bytes not forwarded")
		}
		_ = json.NewEncoder(w).Encode(modelResponse{CatalogVersion: "demo-v1", ModelVersion: "image", Demo: true, Candidates: []modelCandidate{{ID: demoWines[0].ID, Score: 1}}, SelectedID: demoWines[0].ID})
	}))
	defer upstream.Close()
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}})
	rec := request(t, h, http.MethodPost, "/v1/search", `{"photoId":"`+receipt.ID+`"}`)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestSVC006ConfiguredSearchRequiresInputAndFailsClosed(t *testing.T) {
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: &modelClient{configErr: errors.New("bad URL")}})
	if got := request(t, h, http.MethodPost, "/v1/search", `{}`).Code; got != http.StatusBadRequest {
		t.Fatalf("empty input status=%d", got)
	}
	if got := request(t, h, http.MethodPost, "/v1/search", `{"query":"x"}`).Code; got != http.StatusServiceUnavailable {
		t.Fatalf("misconfigured status=%d", got)
	}
}

func TestSVC007RedirectAndUnknownRecommendationAreNotAccepted(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, "/other", http.StatusFound) }))
	defer upstream.Close()
	h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}, recommendations: &modelClient{baseURL: upstream.URL, catalogVersion: "demo-v1", client: noRedirectHTTPClient()}})
	if got := request(t, h, http.MethodPost, "/v1/search", `{"query":"x"}`).Code; got != http.StatusBadGateway {
		t.Fatalf("redirect status=%d", got)
	}
	if got := request(t, h, http.MethodPost, "/v1/recommendations", `{"wineId":"missing"}`).Code; got != http.StatusNotFound {
		t.Fatalf("unknown wine status=%d", got)
	}
}

func TestSVC009CanceledContextReachesUpstreamTransport(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	seen := false
	client := &modelClient{baseURL: "http://example.invalid", catalogVersion: "demo-v1", client: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		seen = true
		if r.Context().Err() == nil {
			t.Fatal("request context was not canceled")
		}
		return nil, r.Context().Err()
	})}}
	_, err := client.request(ctx, "/v1/search/text", "application/json", strings.NewReader(`{}`), time.Second, "")
	if !seen || !errors.Is(err, context.Canceled) {
		t.Fatalf("seen=%t err=%v", seen, err)
	}
}

func TestSVC010RouteCorrelationBudgets(t *testing.T) {
	tests := []struct {
		name     string
		wrap     func(http.HandlerFunc) http.HandlerFunc
		expected time.Duration
	}{
		{name: "search", wrap: correlateSearchRequest, expected: 25 * time.Second},
		{name: "recommendations", wrap: correlateRecommendationRequest, expected: 9 * time.Second},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var remaining time.Duration
			handler := test.wrap(func(w http.ResponseWriter, r *http.Request) {
				deadline, ok := r.Context().Deadline()
				if !ok {
					t.Fatal("route context has no deadline")
				}
				remaining = time.Until(deadline)
				w.WriteHeader(http.StatusNoContent)
			})
			handler(httptest.NewRecorder(), httptest.NewRequest(http.MethodPost, "/v1/"+test.name, nil))
			if remaining < test.expected-time.Second || remaining > test.expected {
				t.Fatalf("deadline remaining=%v, want close to %v", remaining, test.expected)
			}
		})
	}
}
