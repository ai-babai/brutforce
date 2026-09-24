package main

import (
	"bytes"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func visionFixture(t *testing.T) (*app, *http.ServeMux, string) {
	t.Helper()
	root := t.TempDir()
	for _, dir := range []string{"images", "thumbnails"} {
		if e := os.Mkdir(filepath.Join(root, dir), 0700); e != nil {
			t.Fatal(e)
		}
	}
	img := image.NewRGBA(image.Rect(0, 0, 2, 2))
	img.Set(0, 0, color.RGBA{R: 200, A: 255})
	var picture bytes.Buffer
	if e := png.Encode(&picture, img); e != nil {
		t.Fatal(e)
	}
	for _, id := range []string{"bottle", "scene", "result", "other"} {
		for _, dir := range []string{"images", "thumbnails"} {
			if e := os.WriteFile(filepath.Join(root, dir, id+".png"), picture.Bytes(), 0600); e != nil {
				t.Fatal(e)
			}
		}
	}
	rows := []visionImage{
		{ID: "bottle", Slug: "wine-a", Role: "identity_reference", Path: "images/bottle.png", ThumbnailPath: "thumbnails/bottle.png", Origin: "real", QC: visionQC{Status: "accepted"}},
		{ID: "scene", Role: "scene_reference", Path: "images/scene.png", ThumbnailPath: "thumbnails/scene.png", Origin: "real", QC: visionQC{Status: "accepted"}},
		{ID: "result", Slug: "wine-a", Role: "output", Path: "images/result.png", ThumbnailPath: "thumbnails/result.png", Origin: "ai_generated", ScenarioIDs: []string{"table"}, IdentityReferenceID: "bottle", SceneReferenceID: "scene", Model: "model-one", CostUSD: .03, QC: visionQC{Status: "pending"}, Source: json.RawMessage(`{"url":"https://example.org/source","source_id":"s1","relative_path":"private/gold-v1.json","source_locator":"/srv/secret"}`)},
		{ID: "other", Slug: "wine-b", Role: "output", Path: "images/other.png", Origin: "ai_edited", ScenarioIDs: []string{"outdoor"}, Model: "model-two", QC: visionQC{Status: "rejected"}},
	}
	writeVisionRows(t, root, rows)
	a := &app{vision: &visionCatalog{root: root}, participant: "participant", review: "review"}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/data/facets", a.dataFacets)
	mux.HandleFunc("GET /api/data/slugs", a.dataSlugs)
	mux.HandleFunc("GET /api/data/images", a.dataImages)
	mux.HandleFunc("GET /api/data/images/{id}", a.dataImageInfo)
	mux.HandleFunc("GET /api/data/images/{id}/image", a.dataImage)
	mux.HandleFunc("GET /api/data/images/{id}/thumbnail", a.dataThumbnail)
	return a, mux, root
}

func writeVisionRows(t *testing.T, root string, rows []visionImage) {
	t.Helper()
	var data bytes.Buffer
	for _, row := range rows {
		b, e := json.Marshal(row)
		if e != nil {
			t.Fatal(e)
		}
		data.Write(b)
		data.WriteByte('\n')
	}
	if e := os.WriteFile(filepath.Join(root, "manifest.jsonl"), data.Bytes(), 0600); e != nil {
		t.Fatal(e)
	}
}

func TestVisionContractFiltersAndReferences(t *testing.T) {
	_, mux, _ := visionFixture(t)
	if got := request(t, mux, "GET", "/api/data/slugs", "", nil); got.Code != 200 {
		t.Fatalf("unauthenticated data request: %d", got.Code)
	}
	got := request(t, mux, "GET", "/api/data/slugs?page=1&per_page=1", "", nil)
	if got.Code != 200 {
		t.Fatalf("slugs: %d %s", got.Code, got.Body.String())
	}
	var slugs struct {
		Items       []slugSummary `json:"items"`
		TotalSlugs  int           `json:"total_slugs"`
		TotalImages int           `json:"total_images"`
	}
	if e := json.Unmarshal(got.Body.Bytes(), &slugs); e != nil {
		t.Fatal(e)
	}
	if slugs.TotalSlugs != 2 || slugs.TotalImages != 3 || len(slugs.Items) != 1 || slugs.Items[0].Slug != "wine-a" || slugs.Items[0].Total != 2 {
		t.Fatalf("wrong paginated counts: %+v", slugs)
	}
	got = request(t, mux, "GET", "/api/data/slugs?scenario=table&origin=ai_generated&model=model-one&qc=pending", "participant", nil)
	if got.Code != 200 || !strings.Contains(got.Body.String(), `"total_slugs":1`) || !strings.Contains(got.Body.String(), `"total_images":1`) {
		t.Fatalf("combined filters: %d %s", got.Code, got.Body.String())
	}
	got = request(t, mux, "GET", "/api/data/images?slug=wine-a&role=output", "participant", nil)
	if got.Code != 200 || !strings.Contains(got.Body.String(), `"image_id":"result"`) || strings.Contains(got.Body.String(), `"image_id":"bottle"`) {
		t.Fatalf("image filter: %d %s", got.Code, got.Body.String())
	}
	got = request(t, mux, "GET", "/api/data/images/result", "", nil)
	if got.Code != 200 || !strings.Contains(got.Body.String(), `"scene_reference_id":"scene"`) || !strings.Contains(got.Body.String(), `"identity_reference_id":"bottle"`) {
		t.Fatalf("reference links: %d %s", got.Code, got.Body.String())
	}
	for _, secret := range []string{"private/gold-v1.json", "/srv/secret", "source_locator", "relative_path"} {
		if strings.Contains(got.Body.String(), secret) {
			t.Fatalf("private source field leaked: %s", secret)
		}
	}
	if !strings.Contains(got.Body.String(), `"source_id":"s1"`) {
		t.Fatal("safe provenance ID missing")
	}
	got = request(t, mux, "GET", "/api/data/images/scene", "participant", nil)
	if got.Code != 200 || strings.Contains(got.Body.String(), `"slug"`) {
		t.Fatalf("shared scene should have no slug: %d %s", got.Code, got.Body.String())
	}
	got = request(t, mux, "GET", "/api/data/images/result/thumbnail", "", nil)
	if got.Code != 200 || got.Header().Get("Content-Type") != "image/png" || got.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatalf("thumbnail response: %d %s", got.Code, got.Header())
	}
	got = request(t, mux, "GET", "/api/data/images/other/thumbnail", "participant", nil)
	if got.Code != 404 {
		t.Fatalf("missing thumbnail: %d", got.Code)
	}
}

func TestVisionManifestReloadAndInvalidRows(t *testing.T) {
	a, mux, root := visionFixture(t)
	if _, e := a.vision.snapshot(); e != nil {
		t.Fatal(e)
	}
	got := request(t, mux, "GET", "/api/data/slugs?model=model-two", "participant", nil)
	if !strings.Contains(got.Body.String(), `"total_slugs":1`) {
		t.Fatal(got.Body.String())
	}
	rows := []visionImage{{ID: "new", Slug: "new-wine", Role: "output", Path: "images/result.png", Origin: "ai_generated", QC: visionQC{Status: "pending"}}}
	writeVisionRows(t, root, rows)
	got = request(t, mux, "GET", "/api/data/slugs", "participant", nil)
	if got.Code != 200 || !strings.Contains(got.Body.String(), "new-wine") || strings.Contains(got.Body.String(), "wine-a") {
		t.Fatalf("manifest reload: %d %s", got.Code, got.Body.String())
	}
	rows[0].Path = "../eval/private/gold-v1.json"
	writeVisionRows(t, root, rows)
	got = request(t, mux, "GET", "/api/data/slugs", "participant", nil)
	if got.Code != 503 {
		t.Fatalf("traversal manifest served: %d %s", got.Code, got.Body.String())
	}
	rows[0].Path = "images/result.png"
	rows[0].IdentityReferenceID = "missing"
	writeVisionRows(t, root, rows)
	if _, e := readVisionManifest(root); e == nil {
		t.Fatal("unresolved image reference accepted")
	}
}

func TestVisionPathConfinementAndRootSeparation(t *testing.T) {
	_, _, root := visionFixture(t)
	for _, name := range []string{"../secret.jpg", "/tmp/secret.jpg", "images/../../secret.jpg", "images\\secret.jpg", "private/gold.jpg", "images/secret.json"} {
		if _, e := localImagePath(root, name); e == nil {
			t.Fatalf("accepted unsafe path %q", name)
		}
	}
	if e := os.Symlink(filepath.Join(root, "images", "bottle.png"), filepath.Join(root, "images", "linked.png")); e != nil {
		t.Fatal(e)
	}
	if _, e := localImagePath(root, "images/linked.png"); e == nil {
		t.Fatal("accepted symlinked image")
	}
	if !sameOrNestedRoot(root, filepath.Join(root, "nested")) || sameOrNestedRoot(root, filepath.Join(filepath.Dir(root), "sibling")) {
		t.Fatal("root separation check failed")
	}
}

func TestVisionConfiguredCorpus(t *testing.T) {
	root := os.Getenv("LCT_EVAL_TEST_VISION_DATA")
	if root == "" {
		t.Skip("set LCT_EVAL_TEST_VISION_DATA to validate an assembled corpus")
	}
	data, e := readVisionManifest(root)
	if e != nil {
		t.Fatal(e)
	}
	if len(data.images) == 0 {
		t.Fatal("configured corpus is empty")
	}
	t.Logf("validated %d image records", len(data.images))
}
