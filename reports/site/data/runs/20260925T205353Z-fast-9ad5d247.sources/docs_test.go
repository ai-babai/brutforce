package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"testing"
)

func TestAPI017DocsAreLocalAndDeliberateAPIRoutes(t *testing.T) {
	handler := newHandler("")
	for _, item := range []struct {
		path, contentType, contains string
	}{
		{"/api/docs", "text/html", "validatorUrl: null"},
		{"/api/docs/swagger-ui.css", "text/css", ".swagger-ui"},
		{"/api/docs/swagger-ui-bundle.js", "application/javascript", "SwaggerUIBundle"},
		{"/api/openapi.json", "application/json", "\"openapi\": \"3.1.0\""},
		{"/api/schema/demo-search.schema.json", "application/schema+json", "App search success response"},
	} {
		response := request(t, handler, http.MethodGet, item.path, "")
		if response.Code != http.StatusOK || !strings.HasPrefix(response.Header().Get("Content-Type"), item.contentType) || !bytes.Contains(response.Body.Bytes(), []byte(item.contains)) {
			t.Fatalf("GET %s: status=%d content-type=%q", item.path, response.Code, response.Header().Get("Content-Type"))
		}
	}
	for _, item := range []struct {
		method, path string
		want         int
	}{
		{http.MethodPost, "/api/docs", http.StatusMethodNotAllowed},
		{http.MethodGet, "/api/docs/not-a-file", http.StatusNotFound},
	} {
		response := request(t, handler, item.method, item.path, "")
		if response.Code != item.want {
			t.Fatalf("%s %s: status=%d want=%d", item.method, item.path, response.Code, item.want)
		}
		decoded := decodeResponse(t, response)
		if decoded.Error == nil || !decoded.Demo {
			t.Fatalf("%s %s did not return a JSON API error: %+v", item.method, item.path, decoded)
		}
	}
}

func TestAPI018OpenAPIMatchesImplementedDemoContract(t *testing.T) {
	canonical, err := os.ReadFile("../../contracts/demo-search.schema.json")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(canonical, embeddedDemoSearchSchema) {
		t.Fatal("embedded demo-search schema differs from contracts/demo-search.schema.json")
	}

	var spec struct {
		OpenAPI    string                     `json:"openapi"`
		Info       struct{ Version string }   `json:"info"`
		Paths      map[string]json.RawMessage `json:"paths"`
		Components struct {
			Schemas map[string]json.RawMessage `json:"schemas"`
		} `json:"components"`
	}
	if err := json.Unmarshal(openAPISpec, &spec); err != nil {
		t.Fatalf("decode OpenAPI: %v", err)
	}
	if spec.OpenAPI != "3.1.0" || spec.Info.Version != "2.0.0" {
		t.Fatalf("OpenAPI version=%q contract version=%q", spec.OpenAPI, spec.Info.Version)
	}
	wantMethods := map[string]string{
		"/v1/health":          http.MethodGet,
		"/v2/catalog/{slug}":  http.MethodGet,
		"/v2/catalog":         http.MethodGet,
		"/v1/photos":          http.MethodPost,
		"/v1/search":          http.MethodPost,
		"/v1/eval/predict":    http.MethodPost,
		"/v1/recommendations": http.MethodPost,
		"/v1/feedback":        http.MethodPost,
	}
	if len(spec.Paths) != len(wantMethods) {
		t.Fatalf("documented paths=%d want=%d", len(spec.Paths), len(wantMethods))
	}
	for path, method := range wantMethods {
		var operations map[string]json.RawMessage
		if err := json.Unmarshal(spec.Paths[path], &operations); err != nil || len(operations) != 1 || operations[strings.ToLower(method)] == nil {
			t.Fatalf("OpenAPI operation %s %s is missing or invalid: %v", method, path, err)
		}
	}
	for _, name := range []string{"Health", "SearchRequest", "SearchResponse", "PhotoReceipt", "FeedbackRequest", "FeedbackReceipt", "APIError", "EvalPrediction", "EvalError"} {
		if spec.Components.Schemas[name] == nil {
			t.Fatalf("OpenAPI component %s is missing", name)
		}
	}
	if !bytes.Contains(spec.Components.Schemas["SearchResponse"], []byte(`/api/schema/demo-search.schema.json`)) {
		t.Fatal("SearchResponse does not reference the served canonical schema")
	}
	if !bytes.Contains(spec.Components.Schemas["APIError"], []byte(`"candidates"`)) || !bytes.Contains(openAPISpec, []byte(`"query": "каберне"`)) {
		t.Fatal("OpenAPI does not describe the actual error field or a working search example")
	}

	handler := newHandler("")
	for _, item := range []struct {
		method, path, body string
		want               int
	}{
		{http.MethodGet, "/v1/health", "", http.StatusOK},
		{http.MethodGet, "/v2/catalog", "", http.StatusOK},
		{http.MethodPost, "/v1/photos", "", http.StatusServiceUnavailable},
		{http.MethodPost, "/v1/search", `{"scenario":"exact"}`, http.StatusOK},
		{http.MethodPost, "/v1/search", `{"scenario":"error"}`, http.StatusServiceUnavailable},
	} {
		response := request(t, handler, item.method, item.path, item.body)
		if response.Code != item.want {
			t.Fatalf("%s %s: status=%d want=%d body=%s", item.method, item.path, response.Code, item.want, response.Body.String())
		}
		if item.want >= 400 {
			decoded := decodeResponse(t, response)
			if !decoded.Demo || decoded.Error == nil || decoded.Error.Code == "" || decoded.Error.Message == "" || decoded.Candidates != nil {
				t.Fatalf("%s %s error shape: %+v", item.method, item.path, decoded)
			}
		}
	}
}
