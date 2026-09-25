package main

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"lct-eval/internal/eval"
)

func TestPredictWhitespaceArrayIncludesBodyTime(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		f, hdr, e := r.FormFile("image")
		if e != nil {
			t.Errorf("image multipart missing: %v", e)
			w.WriteHeader(400)
			return
		}
		b, _ := io.ReadAll(f)
		f.Close()
		if string(b) != "image" {
			t.Errorf("wrong image %q", b)
		}
		if hdr.Filename != "case-1.png" {
			t.Errorf("filename lost extension: %s", hdr.Filename)
		}
		w.WriteHeader(201)
		w.(http.Flusher).Flush()
		time.Sleep(30 * time.Millisecond)
		w.Write([]byte("  \n [ {\"slug\":\"first\"}, {\"slug\":\"second\"} ]  \n"))
	}))
	defer srv.Close()
	r := predict(&http.Client{Timeout: time.Second}, srv.URL, eval.Case{ID: "case-1", ImagePath: "images/neutral.png"}, []byte("image"), "service")
	if r.Status != "ok" || r.Prediction.Slug != "first" {
		t.Fatalf("array parse: %+v", r)
	}
	if r.LatencyMS < 25 {
		t.Fatalf("latency excludes body: %dms", r.LatencyMS)
	}
}
func TestPredictBodyTimeout(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		w.(http.Flusher).Flush()
		time.Sleep(120 * time.Millisecond)
		w.Write([]byte(`{"slug":"late"}`))
	}))
	defer srv.Close()
	r := predict(&http.Client{Timeout: 45 * time.Millisecond}, srv.URL, eval.Case{ID: "case-1"}, []byte("image"), "service")
	if r.Status != "timeout" {
		t.Fatalf("body timeout classified as %+v", r)
	}
	if r.LatencyMS < 35 {
		t.Fatalf("latency too short: %dms", r.LatencyMS)
	}
}
func TestRunnerPersistsSolutionMetadata(t *testing.T) {
	a, mux := testApp(t)
	evalServer := httptest.NewServer(mux)
	defer evalServer.Close()
	predictServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"slug":"secret-slug"}`))
	}))
	defer predictServer.Close()
	runClient([]string{"-source", "api", "-base", evalServer.URL, "-token", "participant-secret", "-endpoint", predictServer.URL, "-track", "service", "-submission-id", "run-metadata", "-solution", "model", "-solution-version", "2", "-commit", "abc123", "-config-hash", "cfg456", "-weights-version", "weights7", "-catalog-version", "catalog9"})
	a.mu.Lock()
	got := a.runs["run-metadata"].Submission.Solution
	a.mu.Unlock()
	if got.Commit == nil || *got.Commit != "abc123" || got.ConfigHash == nil || *got.ConfigHash != "cfg456" || got.WeightsVersion == nil || *got.WeightsVersion != "weights7" || got.CatalogVersion == nil || *got.CatalogVersion != "catalog9" {
		t.Fatalf("metadata missing: %+v", got)
	}
}
func TestRunnerCanWriteArchivePredictionsWithoutScoringToken(t *testing.T) {
	a, mux := testApp(t)
	archive := request(t, mux, "GET", "/api/baskets/v1/download", "", nil)
	if archive.Code != 200 {
		t.Fatal(archive.Code)
	}
	path := filepath.Join(t.TempDir(), "suite.zip")
	if e := os.WriteFile(path, archive.Body.Bytes(), 0600); e != nil {
		t.Fatal(e)
	}
	output := filepath.Join(t.TempDir(), "predictions.json")
	predictServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"slug":"secret-slug"}`))
	}))
	defer predictServer.Close()
	runClient([]string{"-source", "archive", "-archive", path, "-suite-version", "v1", "-no-submit", "-output", output, "-endpoint", predictServer.URL, "-track", "service", "-submission-id", "offline-1", "-solution", "model", "-solution-version", "2"})
	data, e := os.ReadFile(output)
	if e != nil {
		t.Fatal(e)
	}
	var sub eval.Submission
	if e = json.Unmarshal(data, &sub); e != nil {
		t.Fatal(e)
	}
	if sub.SuiteHash != a.suite.Hash || sub.Results[0].Prediction.Slug != "secret-slug" {
		t.Fatalf("wrong offline predictions: %+v", sub)
	}
	if len(a.runs) != 0 {
		t.Fatal("offline run submitted unexpectedly")
	}
}
