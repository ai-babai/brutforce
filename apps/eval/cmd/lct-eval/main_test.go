package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"lct-eval/internal/eval"
)

func testApp(t *testing.T) (*app, *http.ServeMux) {
	t.Helper()
	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "images"), 0700)
	os.MkdirAll(filepath.Join(root, "baskets"), 0700)
	os.MkdirAll(filepath.Join(root, "private"), 0700)
	image := []byte("image bytes")
	os.WriteFile(filepath.Join(root, "images", "neutral.jpg"), image, 0600)
	ih := sha256.Sum256(image)
	s := eval.Suite{Version: "v1", Cases: []eval.Case{{ID: "IMG-01-001", ImagePath: "images/neutral.jpg", ImageSHA256: hex.EncodeToString(ih[:]), OriginKind: "ai", BasketIDs: []string{"IMG-01"}, Tracks: []string{"service"}}}, Baskets: []eval.Basket{{ID: "IMG-01", Track: "service", Description: "test"}}}
	g := eval.Gold{Version: "v1", Cases: []eval.GoldCase{{ID: "IMG-01-001", Verified: true, Service: &eval.GoldTrack{ExpectedAction: "match", ExpectedSlug: "secret-slug"}}}}
	gHash, _ := eval.ComputeGoldHash(g)
	s.GoldHash = gHash
	s.Hash, _ = eval.ComputeHash(s)
	g.Hash = s.Hash
	sb, _ := json.Marshal(s)
	gb, _ := json.Marshal(g)
	os.WriteFile(filepath.Join(root, "baskets", "v1.json"), sb, 0600)
	os.WriteFile(filepath.Join(root, "private", "gold-v1.json"), gb, 0600)
	loaded, e := eval.LoadSuite(filepath.Join(root, "baskets", "v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = eval.LoadGold(filepath.Join(root, "private", "gold-v1.json"), loaded); e != nil {
		t.Fatal(e)
	}
	a := &app{root: root, suite: s, gold: g, participant: "participant-secret", review: "review-secret", runs: map[string]eval.Report{}, runsPath: filepath.Join(root, "runs.jsonl")}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/baskets", a.baskets)
	mux.HandleFunc("GET /api/baskets/{version}/download", a.download)
	mux.HandleFunc("GET /api/baskets/{version}/cases/{id}", a.caseInfo)
	mux.HandleFunc("GET /api/baskets/{version}/cases/{id}/image", a.image)
	mux.HandleFunc("POST /api/submissions", a.submit)
	mux.HandleFunc("GET /api/runs", a.listRuns)
	return a, mux
}
func request(t *testing.T, h http.Handler, method, path, token string, body []byte) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequest(method, path, bytes.NewReader(body))
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}
func testSubmission(s eval.Suite) eval.Submission {
	return eval.Submission{ID: "run-1", SuiteVersion: s.Version, SuiteHash: s.Hash, Track: "service", BasketIDs: []string{"IMG-01"}, Solution: eval.Solution{Name: "model", Version: "1"}, Results: []eval.Result{{CaseID: "IMG-01-001", Status: "ok", Prediction: eval.Prediction{Slug: "wrong"}}}}
}
func TestPrivacyIdempotencyAndPersistence(t *testing.T) {
	a, mux := testApp(t)
	w := request(t, mux, "GET", "/api/baskets", "", nil)
	if w.Code != 401 {
		t.Fatal(w.Code)
	}
	w = request(t, mux, "GET", "/api/baskets/v1/cases/IMG-01-001", "participant-secret", nil)
	if strings.Contains(w.Body.String(), "secret-slug") {
		t.Fatal("gold leaked in case")
	}
	w = request(t, mux, "GET", "/api/baskets/v1/download", "participant-secret", nil)
	if w.Code != 200 {
		t.Fatal(w.Code)
	}
	archive, e := zip.NewReader(bytes.NewReader(w.Body.Bytes()), int64(w.Body.Len()))
	if e != nil {
		t.Fatal(e)
	}
	for _, f := range archive.File {
		if strings.Contains(f.Name, "private") || strings.Contains(f.Name, "gold") {
			t.Fatalf("gold path in archive: %s", f.Name)
		}
		rc, _ := f.Open()
		b, _ := io.ReadAll(rc)
		rc.Close()
		if bytes.Contains(b, []byte("secret-slug")) {
			t.Fatal("gold leaked in archive")
		}
	}
	sub := testSubmission(a.suite)
	payload, _ := json.Marshal(sub)
	w = request(t, mux, "POST", "/api/submissions", "participant-secret", payload)
	if w.Code != 201 {
		t.Fatalf("submit %d %s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Body.String(), "secret-slug") {
		t.Fatal("gold leaked in participant report")
	}
	first, _ := os.ReadFile(a.runsPath)
	w = request(t, mux, "POST", "/api/submissions", "participant-secret", payload)
	if w.Code != 200 {
		t.Fatalf("idempotency %d", w.Code)
	}
	second, _ := os.ReadFile(a.runsPath)
	if !bytes.Equal(first, second) {
		t.Fatal("idempotent resend appended")
	}
	w = request(t, mux, "GET", "/api/runs", "review-secret", nil)
	if !strings.Contains(w.Body.String(), "secret-slug") {
		t.Fatal("review missing gold")
	}
	if strings.Contains(string(first), "secret-slug") {
		t.Fatal("gold persisted in runs")
	}
	sub.Results[0].Prediction.Slug = "different"
	payload, _ = json.Marshal(sub)
	w = request(t, mux, "POST", "/api/submissions", "participant-secret", payload)
	if w.Code != 409 {
		t.Fatalf("conflict %d", w.Code)
	}
	reloaded := &app{runs: map[string]eval.Report{}, runsPath: a.runsPath}
	if e = reloaded.loadRuns(); e != nil || len(reloaded.runs) != 1 {
		t.Fatalf("restart: %v %d", e, len(reloaded.runs))
	}
}
func TestInvalidHashUnknownAndDamagedTail(t *testing.T) {
	a, mux := testApp(t)
	sub := testSubmission(a.suite)
	sub.SuiteHash = "wrong"
	b, _ := json.Marshal(sub)
	w := request(t, mux, "POST", "/api/submissions", "participant-secret", b)
	if w.Code != 400 {
		t.Fatal("wrong hash accepted")
	}
	sub = testSubmission(a.suite)
	sub.Results[0].CaseID = "unknown"
	b, _ = json.Marshal(sub)
	w = request(t, mux, "POST", "/api/submissions", "participant-secret", b)
	if w.Code != 400 {
		t.Fatal("unknown case accepted")
	}
	os.WriteFile(a.runsPath, []byte("{bad"), 0600)
	reloaded := &app{runs: map[string]eval.Report{}, runsPath: a.runsPath, suite: a.suite, gold: a.gold, participant: a.participant, review: a.review}
	if e := reloaded.loadRuns(); e != nil {
		t.Fatal(e)
	}
	if !reloaded.tailCorrupt {
		t.Fatal("tail not detected")
	}
	mux2 := http.NewServeMux()
	mux2.HandleFunc("POST /api/submissions", reloaded.submit)
	sub = testSubmission(a.suite)
	b, _ = json.Marshal(sub)
	w = request(t, mux2, "POST", "/api/submissions", "participant-secret", b)
	if w.Code != 503 {
		t.Fatal("accepted submission on damaged history")
	}
}
func TestPublicManifestRejectsUnknownFieldsAndPrivateSymlink(t *testing.T) {
	a, _ := testApp(t)
	sp := filepath.Join(a.root, "baskets", "v1.json")
	b, e := os.ReadFile(sp)
	if e != nil {
		t.Fatal(e)
	}
	modified := bytes.Replace(b, []byte(`"version":"v1"`), []byte(`"version":"v1","expected_slug":"secret-slug"`), 1)
	if bytes.Equal(modified, b) {
		t.Fatal("fixture replace failed")
	}
	os.WriteFile(sp, modified, 0600)
	if _, e = eval.LoadSuite(sp); e == nil {
		t.Fatal("accepted unknown public field")
	}
	os.WriteFile(sp, b, 0600)
	os.Remove(filepath.Join(a.root, "images", "neutral.jpg"))
	os.Symlink(filepath.Join(a.root, "private", "gold-v1.json"), filepath.Join(a.root, "images", "neutral.jpg"))
	goldBytes, _ := os.ReadFile(filepath.Join(a.root, "private", "gold-v1.json"))
	h := sha256.Sum256(goldBytes)
	a.suite.Cases[0].ImageSHA256 = hex.EncodeToString(h[:])
	a.suite.Hash, _ = eval.ComputeHash(a.suite)
	manifest, _ := json.Marshal(a.suite)
	os.WriteFile(sp, manifest, 0600)
	if _, e = eval.LoadSuite(sp); e == nil {
		t.Fatal("accepted private symlink as image")
	}
}
