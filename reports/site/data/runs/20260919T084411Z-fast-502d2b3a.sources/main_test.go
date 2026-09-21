package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func request(t *testing.T, handler http.Handler, method, target, body string) *httptest.ResponseRecorder {
	t.Helper()
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(method, target, strings.NewReader(body)))
	return recorder
}

func decodeResponse(t *testing.T, recorder *httptest.ResponseRecorder) searchResponse {
	t.Helper()
	var response searchResponse
	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("decode response: %v; body=%q", err, recorder.Body.String())
	}
	return response
}

func TestAPI001ExactSelectsCabernet(t *testing.T) {
	recorder := request(t, newHandler(""), http.MethodPost, "/api/search", `{"scenario":"exact"}`)
	response := decodeResponse(t, recorder)
	if recorder.Code != http.StatusOK || !response.Demo || len(response.Candidates) != 2 || response.SelectedID != demoWines[0].ID {
		t.Fatalf("exact: status=%d response=%+v", recorder.Code, response)
	}
}

func TestAPI002UncertainReturnsCandidatesWithoutSelection(t *testing.T) {
	recorder := request(t, newHandler(""), http.MethodPost, "/api/search", `{"scenario":"uncertain"}`)
	response := decodeResponse(t, recorder)
	if recorder.Code != http.StatusOK || len(response.Candidates) != 2 || response.SelectedID != "" {
		t.Fatalf("uncertain: status=%d response=%+v", recorder.Code, response)
	}
}

func TestAPI003NoneReturnsEmptyCandidates(t *testing.T) {
	recorder := request(t, newHandler(""), http.MethodPost, "/api/search", `{"scenario":"none"}`)
	response := decodeResponse(t, recorder)
	if recorder.Code != http.StatusOK || response.Candidates == nil || len(response.Candidates) != 0 {
		t.Fatalf("none: status=%d response=%+v", recorder.Code, response)
	}
}

func TestAPI004ErrorIsStructured503(t *testing.T) {
	recorder := request(t, newHandler(""), http.MethodPost, "/api/search", `{"scenario":"error"}`)
	response := decodeResponse(t, recorder)
	if recorder.Code != http.StatusServiceUnavailable || response.Error == nil || response.Error.Code != "demo_search_unavailable" {
		t.Fatalf("error: status=%d response=%+v", recorder.Code, response)
	}
}

func TestAPI005ManualQueryFiltersCaseInsensitively(t *testing.T) {
	for _, item := range []struct {
		query string
		want  string
	}{
		{query: "мЕрЛо", want: demoWines[1].ID},
		{query: "ДЕМО-ВИНОДЕЛЬНЯ", want: demoWines[0].ID},
	} {
		recorder := request(t, newHandler(""), http.MethodPost, "/api/search", `{"query":"`+item.query+`"}`)
		response := decodeResponse(t, recorder)
		if recorder.Code != http.StatusOK || len(response.Candidates) == 0 || response.SelectedID != item.want {
			t.Fatalf("query %q: status=%d response=%+v", item.query, recorder.Code, response)
		}
	}
}

func TestAPI006InvalidInputIs400(t *testing.T) {
	for _, body := range []string{`{`, `null`, `{"scenario":"other"}`, `{"query":" "}`} {
		recorder := request(t, newHandler(""), http.MethodPost, "/api/search", body)
		response := decodeResponse(t, recorder)
		if recorder.Code != http.StatusBadRequest || response.Error == nil {
			t.Fatalf("invalid body %q: status=%d response=%+v", body, recorder.Code, response)
		}
	}
}

func TestAPI007MethodAndUnknownAPIRouteReturnJSON4xx(t *testing.T) {
	handler := newHandler("")
	for _, item := range []struct {
		method, target string
		want           int
	}{
		{http.MethodGet, "/api/search", http.StatusMethodNotAllowed},
		{http.MethodGet, "/api/unknown", http.StatusNotFound},
	} {
		recorder := request(t, handler, item.method, item.target, "")
		response := decodeResponse(t, recorder)
		if recorder.Code != item.want || response.Error == nil || !strings.HasPrefix(recorder.Header().Get("Content-Type"), "application/json") {
			t.Fatalf("%s %s: status=%d response=%+v", item.method, item.target, recorder.Code, response)
		}
	}
}

func TestAPI008Health(t *testing.T) {
	recorder := request(t, newHandler(""), http.MethodGet, "/api/health", "")
	var health map[string]bool
	if err := json.NewDecoder(recorder.Body).Decode(&health); err != nil {
		t.Fatal(err)
	}
	if recorder.Code != http.StatusOK || !health["ok"] || !health["demo"] {
		t.Fatalf("health: status=%d response=%+v", recorder.Code, health)
	}
}

func TestSearchBodyLimit(t *testing.T) {
	body := bytes.Repeat([]byte("x"), maxRequestBody+1)
	recorder := httptest.NewRecorder()
	newHandler("").ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/api/search", bytes.NewReader(body)))
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("body limit: status=%d", recorder.Code)
	}
}

func TestSPAHandlerServesFilesAndFallsBackToIndex(t *testing.T) {
	webRoot := t.TempDir()
	if err := os.WriteFile(filepath.Join(webRoot, "index.html"), []byte("demo SPA"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(webRoot, "asset.txt"), []byte("asset"), 0o600); err != nil {
		t.Fatal(err)
	}
	handler := newHandler(webRoot)
	for _, item := range []struct{ target, want string }{
		{"/asset.txt", "asset"},
		{"/client/route", "demo SPA"},
	} {
		recorder := request(t, handler, http.MethodGet, item.target, "")
		if recorder.Code != http.StatusOK || recorder.Body.String() != item.want {
			t.Fatalf("%s: status=%d body=%q", item.target, recorder.Code, recorder.Body.String())
		}
	}
}
