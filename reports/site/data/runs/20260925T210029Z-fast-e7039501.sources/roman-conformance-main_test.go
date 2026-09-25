package main

import (
	"brutforce-behavior-demo/apps/api/internal/referenceengine"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSVC010ConformanceRunsAgainstSeparateReferenceServices(t *testing.T) {
	handler := referenceengine.Handler()
	search := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/recommendations" {
			t.Error("recommendations sent to search address")
		}
		handler.ServeHTTP(w, r)
	}))
	defer search.Close()
	recs := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/recommendations" {
			t.Error("search sent to recommendation address")
		}
		handler.ServeHTTP(w, r)
	}))
	defer recs.Close()
	t.Setenv("SEARCH_SERVICE_URL", search.URL)
	t.Setenv("RECOMMENDATION_SERVICE_URL", recs.URL)
	t.Setenv("CATALOG_VERSION", "demo-v1")
	if err := run(); err != nil {
		t.Fatal(err)
	}
}
