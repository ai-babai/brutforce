package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestSEC006SearchInputBounds(t *testing.T) {
	for _, body := range []string{`{"query":"` + strings.Repeat("я", 257) + `"}`, `{"query":"hello\u0000world"}`, `{"query":"hello\nworld"}`, "{\"query\":\"\xff\"}", strings.Repeat(" ", maxRequestBody+1), `{"query":"wine"} {}`, `{"unexpected":true}`} {
		r := request(t, newHandler(""), "POST", "/v1/search", body)
		if r.Code != 400 {
			t.Fatalf("invalid input accepted: %d", r.Code)
		}
	}
	for _, q := range []string{strings.Repeat("я", 256), "<script>alert(1)</script>", "' OR 1=1 --"} {
		r := request(t, newHandler(""), "POST", "/v1/search", `{"query":"`+q+`"}`)
		if r.Code != 200 {
			t.Fatalf("ordinary bounded text should be data: %d", r.Code)
		}
		if strings.Contains(r.Body.String(), "<script>") {
			t.Fatal("raw input reflected")
		}
	}
}

func TestSEC007RequestBudgetsAndWriteBoundary(t *testing.T) {
	now := time.Unix(100, 0)
	called := 0
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { called++; w.WriteHeader(204) })
	h := protectRequests(next, func() time.Time { return now })
	invoke := func(path, content, encoding, origin string) *httptest.ResponseRecorder {
		r := httptest.NewRequest("POST", path, strings.NewReader("{}"))
		r.Header.Set("Content-Type", content)
		r.Header.Set("Content-Encoding", encoding)
		r.Header.Set("Origin", origin)
		r.Header.Set("X-Forwarded-For", "1.2.3.4")
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w
	}
	if invoke("/v1/search", "text/plain", "", "").Code != 415 {
		t.Fatal("non JSON accepted")
	}
	if invoke("/v1/search", "application/json", "gzip", "").Code != 415 {
		t.Fatal("compressed body accepted")
	}
	if invoke("/v1/feedback", "text/plain", "", "").Code != 415 {
		t.Fatal("non JSON feedback accepted")
	}
	if invoke("/v1/feedback", "application/json", "", "https://evil.example").Code != 403 {
		t.Fatal("cross-origin feedback accepted")
	}
	if invoke("/v1/photos", "multipart/form-data", "", "https://evil.example").Code != 403 {
		t.Fatal("cross-origin write accepted")
	}
	if called != 0 {
		t.Fatal("rejected request reached handler")
	}
	for i := 0; i < 10; i++ {
		if invoke("/v1/search", "application/json", "", "").Code != 204 {
			t.Fatal("budget rejected too early")
		}
	}
	w := invoke("/v1/search", "application/json", "", "")
	if w.Code != 429 || w.Header().Get("Retry-After") != "1" {
		t.Fatal("search budget missing")
	}
	now = now.Add(time.Second)
	if invoke("/v1/search", "application/json", "", "").Code != 204 {
		t.Fatal("budget not replenished")
	}
	for i := 0; i < 4; i++ {
		if invoke("/v1/photos", "multipart/form-data", "", "").Code != 204 {
			t.Fatal("upload budget rejected too early")
		}
	}
	if invoke("/v1/photos", "multipart/form-data", "", "").Code != 429 {
		t.Fatal("upload budget missing")
	}
	now = now.Add(5 * time.Second)
	if invoke("/v1/photos", "multipart/form-data", "", "").Code != 204 {
		t.Fatal("upload budget not replenished")
	}
}

func TestSEC008PrivateUploadsAndHeaders(t *testing.T) {
	dir := t.TempDir()
	web := filepath.Join(dir, "web")
	if e := os.Mkdir(web, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(web, "index.html"), []byte("app"), 0600); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, "private.bin"), []byte("SECRET_PHOTO_SENTINEL"), 0600); e != nil {
		t.Fatal(e)
	}
	h := newHandler(web)
	for _, path := range []string{"/v1/photos", "/v1/photos/123", "/private.bin", "/../private.bin", "/assets/../../private.bin"} {
		w := request(t, h, "GET", path, "")
		if strings.Contains(w.Body.String(), "SECRET_PHOTO_SENTINEL") {
			t.Fatalf("private file exposed: %s", path)
		}
		if w.Header().Get("X-Content-Type-Options") != "nosniff" || w.Header().Get("X-Frame-Options") != "DENY" {
			t.Fatal("security headers missing")
		}
	}
	w := request(t, h, "POST", "/v1/search", `{"photoId":"../../private.bin"}`)
	if w.Code != 400 {
		t.Fatal("traversal photoId accepted")
	}
}
