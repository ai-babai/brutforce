package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"brutforce-behavior-demo/apps/api/internal/referenceengine"
)

type failingModelBody struct{}

func (failingModelBody) Read([]byte) (int, error) { return 0, context.DeadlineExceeded }
func (failingModelBody) Close() error             { return nil }

func TestSVC009FailureBudgetsAndRecommendationIsolation(t *testing.T) {
	good := `{"catalogVersion":"demo-v1","modelVersion":"m1","demo":true,"candidates":[]}`
	for _, tc := range []struct {
		name        string
		status      int
		body        string
		err         error
		readTimeout bool
		want        int
	}{
		{"unreachable", 0, "", errors.New("unreachable"), false, 503},
		{"deadline", 0, "", context.DeadlineExceeded, false, 504},
		{"canceled", 0, "", context.Canceled, false, 408},
		{"busy", 429, "", nil, false, 503}, {"unavailable", 503, "", nil, false, 503},
		{"provider timeout", 504, "", nil, false, 504}, {"incompatible", 409, "", nil, false, 502},
		{"oversize", 200, strings.Repeat("x", (64<<10)+1), nil, false, 502},
		{"body deadline", 200, "", nil, true, 504},
	} {
		t.Run(tc.name, func(t *testing.T) {
			transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
				deadline, ok := r.Context().Deadline()
				remaining := time.Until(deadline)
				if !ok || remaining > time.Second || remaining <= 0 {
					t.Fatalf("missing 1s provider budget: %v", remaining)
				}
				if !safeRequestID(r.Header.Get("X-Request-ID")) {
					t.Error("missing generated request ID")
				}
				if tc.err != nil {
					return nil, tc.err
				}
				body := io.ReadCloser(io.NopCloser(strings.NewReader(tc.body)))
				if tc.readTimeout {
					body = failingModelBody{}
				}
				return &http.Response{StatusCode: tc.status, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: body}, nil
			})
			bad := &modelClient{baseURL: "http://recommendation.invalid", catalogVersion: "demo-v1", client: &http.Client{Transport: transport}}
			goodClient := &modelClient{baseURL: "http://search.invalid", catalogVersion: "demo-v1", client: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(good))}, nil
			})}}
			h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: goodClient, recommendations: bad})
			result := request(t, h, http.MethodPost, "/v1/recommendations", `{"wineId":"demo-cabernet-sauvignon-2023"}`)
			if result.Code != tc.want {
				t.Fatalf("status=%d want=%d body=%s", result.Code, tc.want, result.Body.String())
			}
			if request(t, h, http.MethodPost, "/v1/search", `{"query":"Каберне"}`).Code != 200 {
				t.Fatal("recommendation failure affected search")
			}
		})
	}
}

func TestSVC002MalformedRankedResultsAreNeverPartialSuccess(t *testing.T) {
	first, second := demoWines[0].ID, demoWines[1].ID
	for _, tc := range []struct {
		name     string
		items    []modelCandidate
		selected string
	}{
		{"unknown", []modelCandidate{{ID: "unknown", Score: 1}}, ""},
		{"duplicates", []modelCandidate{{ID: first, Score: 1}, {ID: first, Score: .5}}, ""},
		{"wrong order", []modelCandidate{{ID: first, Score: .1}, {ID: second, Score: .9}}, ""},
		{"bad score", []modelCandidate{{ID: first, Score: 1.1}}, ""},
		{"unknown selection", []modelCandidate{{ID: first, Score: 1}}, second},
		{"more than requested", []modelCandidate{{ID: demoWines[0].ID, Score: 1}, {ID: demoWines[1].ID, Score: .9}, {ID: demoWines[2].ID, Score: .8}, {ID: demoWines[3].ID, Score: .7}, {ID: demoWines[4].ID, Score: .6}, {ID: demoWines[5].ID, Score: .5}}, ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			payload, _ := json.Marshal(modelResponse{CatalogVersion: "demo-v1", ModelVersion: "m", Demo: true, Candidates: tc.items, SelectedID: tc.selected})
			client := &modelClient{baseURL: "http://search.invalid", catalogVersion: "demo-v1", client: &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(string(payload)))}, nil
			})}}
			h := newHandlerWithCatalogAndServices("", nil, embeddedCatalogStore{}, modelServices{search: client})
			if got := request(t, h, http.MethodPost, "/v1/search", `{"query":"x"}`).Code; got != 502 {
				t.Fatalf("got%d", got)
			}
		})
	}
}
func TestSVC004ReferenceCatalogAndRequestBoundaries(t *testing.T) {
	for i, id := range referenceengine.IDs {
		if i >= len(demoWines) || id != demoWines[i].ID {
			t.Fatal("reference IDs drifted from catalog")
		}
	}
	if len(referenceengine.IDs) != len(demoWines) {
		t.Fatal("reference catalog size drift")
	}
	h := referenceengine.Handler()
	for _, tc := range []struct {
		body   string
		status int
	}{
		{`{"query":"Мерло","catalogVersion":"demo-v1"}`, 200},
		{`{"query":"not-a-wine","catalogVersion":"demo-v1"}`, 200},
		{`{"query":"x","catalogVersion":"demo-v1","limit":null}`, 400},
		{`{"query":"x\u0085","catalogVersion":"demo-v1"}`, 400},
		{`{"query":"x","catalogVersion":"demo-v1"}` + strings.Repeat(" ", 64<<10), 400},
	} {
		r := httptest.NewRequest("POST", "/v1/search/text", strings.NewReader(tc.body))
		r.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != tc.status {
			t.Fatalf("status%d want%d", w.Code, tc.status)
		}
		if tc.status == 200 {
			result, err := referenceengine.DecodeResponse(w.Body.Bytes())
			if err != nil {
				t.Fatal(err)
			}
			if strings.Contains(tc.body, "Мерло") && (len(result.Candidates) != 1 || result.Candidates[0].ID != demoWines[1].ID) {
				t.Fatal("reference Cyrillic text search failed")
			}
			if strings.Contains(tc.body, "not-a-wine") && len(result.Candidates) != 0 {
				t.Fatal("reference no-match is not empty")
			}
		}
	}
}
