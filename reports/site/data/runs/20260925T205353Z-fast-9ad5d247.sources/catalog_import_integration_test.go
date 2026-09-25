//go:build integration

package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"brutforce-behavior-demo/apps/api/internal/catalogimport"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

const catalogImportTinyWebP = "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v3AgAA="
const catalogImportTinyWebPSHA = "2c8e008a6a06d559032d6fa985a99d83cac9fe1ddbe8512f98620e70ab3ebd0b"

func integrationPackage(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	public := filepath.Join(root, "public")
	if err := os.MkdirAll(filepath.Join(public, "images"), 0755); err != nil {
		t.Fatal(err)
	}
	b, _ := base64.StdEncoding.DecodeString(catalogImportTinyWebP)
	if err := os.WriteFile(filepath.Join(public, "images", "wine.webp"), b, 0644); err != nil {
		t.Fatal(err)
	}
	wines := fmt.Sprintf(`[{"id":"imported-synthetic-id","slug":"imported-synthetic-wine","title":"Imported synthetic wine","producer":"Test cellar","source_url":"https://example.test/imported","image":{"path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44,"variants":[{"role":"thumbnail","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"card","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"original","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44}]},"alcohol_percent":108}]`, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA)
	if err := os.WriteFile(filepath.Join(public, "wines.json"), []byte(wines), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(public, "aliases.json"), []byte(`{"aliases":[{"alias_slug":"old-imported-synthetic-wine","canonical_slug":"imported-synthetic-wine"}]}`), 0644); err != nil {
		t.Fatal(err)
	}
	return root
}

func acceptedIntegrationPackage(t *testing.T, version string) (string, string) {
	t.Helper()
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "internal"), 0755); err != nil {
		t.Fatal(err)
	}
	sha := strings.Repeat("a", 64)
	wines := fmt.Sprintf(`{"id":"accepted-id","slug":"accepted-slug","title":"Accepted wine","producer":"Test cellar","source_url":"https://example.test/accepted","ratings":[],"image":{"path":"original/%[1]s.webp","sha256":"%[1]s","mime_type":"image/webp","width":1000,"height":500,"bytes":100,"variants":[{"role":"thumbnail","path":"400/%[1]s.webp","sha256":"%[1]s","mime_type":"image/webp","width":400,"height":200,"bytes":40},{"role":"card","path":"800/%[1]s.webp","sha256":"%[1]s","mime_type":"image/webp","width":800,"height":400,"bytes":80},{"role":"original","path":"original/%[1]s.webp","sha256":"%[1]s","mime_type":"image/webp","width":1000,"height":500,"bytes":100}]}}`, sha)
	files := map[string]string{
		"wines.jsonl":                  wines + "\n",
		"aliases.json":                 `{"aliases":[]}`,
		"catalog.json":                 `{"schema_version":"svoe-display-catalog-2.0.0"}`,
		"internal/display-policy.json": `{"schema_version":"catalog-display-policy-1","source_manifest_sha256":"source","suppressed_fields":[]}`,
		"PREPARATION.md":               "accepted fixture\n",
	}
	for path, content := range files {
		if err := os.WriteFile(filepath.Join(root, path), []byte(content), 0644); err != nil {
			t.Fatal(err)
		}
	}
	manifestFiles := make([]map[string]any, 0, len(files))
	for _, path := range []string{"wines.jsonl", "aliases.json", "catalog.json", "internal/display-policy.json", "PREPARATION.md"} {
		manifestFiles = append(manifestFiles, map[string]any{"path": path, "sha256": sha, "bytes": len(files[path])})
	}
	media := []map[string]any{}
	for _, item := range []struct {
		dir           string
		width, height int
		bytes         int
	}{{"400", 400, 200, 40}, {"800", 800, 400, 80}, {"original", 1000, 500, 100}} {
		media = append(media, map[string]any{"path": item.dir + "/" + sha + ".webp", "sha256": sha, "bytes": item.bytes, "width": item.width, "height": item.height, "mime_type": "image/webp"})
	}
	manifest, _ := json.Marshal(map[string]any{"schema_version": "catalog-release-1", "catalog_version": version, "files": manifestFiles, "media": media})
	if err := os.WriteFile(filepath.Join(root, "manifest.json"), manifest, 0644); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(manifest)
	cases := []catalogimport.QualityCase{}
	for _, id := range []string{"DQ001", "DQ002", "DQ003", "DQ004", "DQ005", "DQ006", "DQ007", "DQ008", "DQ011"} {
		cases = append(cases, catalogimport.QualityCase{ID: id, Status: "passed"})
	}
	report := catalogimport.QualityReport{SchemaVersion: 1, Kind: "catalog-data-quality", Status: "passed", CatalogVersion: version, ManifestSHA256: hex.EncodeToString(sum[:]), ValidatorVersion: "test-validator", Counts: map[string]int{}, Cases: cases}
	rawReport, _ := json.Marshal(report)
	reportPath := filepath.Join(t.TempDir(), "accepted.json")
	if err := os.WriteFile(reportPath, rawReport, 0600); err != nil {
		t.Fatal(err)
	}
	return root, reportPath
}

func TestCAT009AcceptedImportRetainsSameVersionDriftCheck(t *testing.T) {
	prepareDatabase(t)
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ctx := context.Background()
	before, err := catalogimport.Export(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := catalogimport.Restore(ctx, db, before); err != nil {
			t.Errorf("restore: %v", err)
		}
	}()
	const version = "accepted-test-v1"
	pkg, report := acceptedIntegrationPackage(t, version)
	opts := catalogimport.Options{PackageDir: pkg, Version: version}
	if _, err := catalogimport.ImportAccepted(ctx, db, opts, report, "test-validator"); err != nil {
		t.Fatal(err)
	}
	expectedWines, expectedAliases, expectedSHA, _, err := catalogimport.LoadAcceptedProjection(opts, report, "test-validator")
	if err != nil {
		t.Fatal(err)
	}
	actual, err := catalogimport.Export(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	if actual.ManifestSHA256 != expectedSHA || !reflect.DeepEqual(actual.Wines, expectedWines) || !reflect.DeepEqual(actual.Aliases, expectedAliases) {
		t.Fatalf("accepted import projection mismatch: actual=%#v expectedWines=%#v expectedAliases=%#v expectedSHA=%s", actual, expectedWines, expectedAliases, expectedSHA)
	}
	if _, err := catalogimport.ImportAccepted(ctx, db, opts, report, "test-validator"); err != nil {
		t.Fatalf("idempotent accepted import failed: %v", err)
	}
	if _, err := db.ExecContext(ctx, "UPDATE catalog_items SET name='drifted' WHERE id='accepted-id'"); err != nil {
		t.Fatal(err)
	}
	if _, err := catalogimport.ImportAccepted(ctx, db, opts, report, "test-validator"); err == nil {
		t.Fatal("accepted same-version import ignored active drift")
	}
}

func TestCAT009ImportIsAtomicIdempotentAndRestorable(t *testing.T) {
	prepareDatabase(t)
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal("migration database unavailable")
	}
	defer db.Close()
	ctx := context.Background()
	before, err := catalogimport.Export(ctx, db)
	if err != nil {
		t.Fatal("cannot export seed snapshot")
	}
	defer func() {
		if err := catalogimport.Restore(ctx, db, before); err != nil {
			t.Errorf("restore initial test snapshot: %v", err)
		}
	}()
	pkg := integrationPackage(t)
	if result, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: pkg, Version: "test-import-v2", DryRun: true}); err != nil || !result.DryRun {
		t.Fatalf("dry run: result=%#v err=%v", result, err)
	}
	afterDryRun, err := catalogimport.Export(ctx, db)
	if err != nil || !reflect.DeepEqual(afterDryRun, before) {
		t.Fatal("dry run mutated active catalog")
	}
	if _, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: pkg, Version: "test-import-v2"}); err != nil {
		t.Fatal(err)
	}
	if _, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: pkg, Version: "test-import-v2"}); err != nil {
		t.Fatal("same version should be idempotent")
	}
	after, err := catalogimport.Export(ctx, db)
	if err != nil {
		t.Fatal(err)
	}
	if after.Version != "test-import-v2" || after.ManifestSHA256 == "" || len(after.Wines) != 1 || after.Wines[0].ID != "imported-synthetic-id" || after.Wines[0].Slug != "imported-synthetic-wine" || after.Wines[0].Year != 0 || after.Wines[0].AlcoholPercent != nil || len(after.Aliases) != 1 {
		t.Fatalf("unexpected imported snapshot: %#v", after)
	}
	t.Run("CAT006PostgresAliasAndCanonicalPage", func(t *testing.T) {
		store, closeStore := realCatalog(t)
		defer closeStore()
		h := newHandlerWithCatalog("", nil, store)
		r := request(t, h, http.MethodGet, "/v2/catalog/old-imported-synthetic-wine", "")
		var body struct {
			Candidate   map[string]any
			CanonicalID string `json:"canonicalId"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if r.Code != 200 || body.CanonicalID != "imported-synthetic-wine" || body.Candidate["id"] != "imported-synthetic-id" {
			t.Fatalf("alias lookup failed: %d %+v", r.Code, body)
		}
		if _, exists := body.Candidate["year"]; exists {
			t.Fatal("unknown year must be omitted")
		}
		page := request(t, h, http.MethodGet, "/v2/catalog", "")
		var listing struct{ Candidates []wine }
		if err := json.NewDecoder(page.Body).Decode(&listing); err != nil {
			t.Fatal(err)
		}
		if page.Code != 200 || len(listing.Candidates) != 1 || listing.Candidates[0].ID != "imported-synthetic-id" || listing.Candidates[0].Slug != body.CanonicalID {
			t.Fatal("alias appeared as a duplicate catalog row")
		}
		missing := request(t, h, http.MethodGet, "/v2/catalog/no-such-slug", "")
		if missing.Code != 404 {
			t.Fatalf("unknown slug returned %d", missing.Code)
		}
	})
	if _, err := db.ExecContext(ctx, "UPDATE catalog_items SET name='drifted' WHERE id='imported-synthetic-id'"); err != nil {
		t.Fatal(err)
	}
	if _, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: pkg, Version: "test-import-v2"}); err == nil {
		t.Fatal("same version accepted drifted active content")
	}
	if _, err := db.ExecContext(ctx, "UPDATE catalog_items SET name='Imported synthetic wine' WHERE id='imported-synthetic-id'"); err != nil {
		t.Fatal(err)
	}
	if err := catalogdb.Seed(ctx, db, "migrations"); err != nil {
		t.Fatal("seed reapply failed")
	}
	afterSeed, err := catalogimport.Export(ctx, db)
	if err != nil || !reflect.DeepEqual(afterSeed, after) {
		t.Fatal("seed changed imported catalog")
	}
	if _, err := db.ExecContext(ctx, `CREATE OR REPLACE FUNCTION catalog_import_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id = 'imported-synthetic-id' THEN RAISE EXCEPTION 'test injected import failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER catalog_import_test_failure BEFORE INSERT ON catalog_items FOR EACH ROW EXECUTE FUNCTION catalog_import_test_fail()`); err != nil {
		t.Fatal("cannot install transaction rollback trigger")
	}
	defer db.ExecContext(ctx, "DROP TRIGGER IF EXISTS catalog_import_test_failure ON catalog_items; DROP FUNCTION IF EXISTS catalog_import_test_fail()")
	if _, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: pkg, Version: "test-import-failure-v2"}); err == nil {
		t.Fatal("injected import failure unexpectedly succeeded")
	}
	afterFailure, err := catalogimport.Export(ctx, db)
	if err != nil || !reflect.DeepEqual(afterFailure, after) {
		t.Fatal("failed import mutated prior snapshot")
	}
	if err := catalogimport.Restore(ctx, db, before); err != nil {
		t.Fatal(err)
	}
	restored, err := catalogimport.Export(ctx, db)
	if err != nil || !reflect.DeepEqual(restored, before) {
		t.Fatal("restore did not retain the complete prior snapshot")
	}
}
