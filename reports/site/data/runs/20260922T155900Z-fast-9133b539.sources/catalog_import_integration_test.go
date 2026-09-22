//go:build integration

package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"brutforce-behavior-demo/apps/api/internal/catalogimport"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
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
	wines := fmt.Sprintf(`[{"slug":"imported-synthetic-wine","title":"Imported synthetic wine","producer":"Test cellar","source_url":"https://example.test/imported","image":{"path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44,"variants":[{"role":"thumbnail","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"card","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"original","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44}]},"alcohol_percent":108}]`, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA, catalogImportTinyWebPSHA)
	if err := os.WriteFile(filepath.Join(public, "wines.json"), []byte(wines), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(public, "aliases.json"), []byte(`{"aliases":[{"alias_slug":"old-imported-synthetic-wine","canonical_slug":"imported-synthetic-wine"}]}`), 0644); err != nil {
		t.Fatal(err)
	}
	return root
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
	if after.Version != "test-import-v2" || len(after.Wines) != 1 || after.Wines[0].ID != "imported-synthetic-wine" || after.Wines[0].Year != 0 || after.Wines[0].AlcoholPercent != nil || len(after.Aliases) != 1 {
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
		if r.Code != 200 || body.CanonicalID != "imported-synthetic-wine" || body.Candidate["id"] != body.CanonicalID {
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
		if page.Code != 200 || len(listing.Candidates) != 1 || listing.Candidates[0].ID != body.CanonicalID {
			t.Fatal("alias appeared as a duplicate catalog row")
		}
		missing := request(t, h, http.MethodGet, "/v2/catalog/no-such-slug", "")
		if missing.Code != 404 {
			t.Fatalf("unknown slug returned %d", missing.Code)
		}
	})
	if err := catalogdb.Seed(ctx, db, "migrations"); err != nil {
		t.Fatal("seed reapply failed")
	}
	afterSeed, err := catalogimport.Export(ctx, db)
	if err != nil || !reflect.DeepEqual(afterSeed, after) {
		t.Fatal("seed changed imported catalog")
	}
	if _, err := db.ExecContext(ctx, `CREATE OR REPLACE FUNCTION catalog_import_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id = 'imported-synthetic-wine' THEN RAISE EXCEPTION 'test injected import failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER catalog_import_test_failure BEFORE INSERT ON demo_catalog FOR EACH ROW EXECUTE FUNCTION catalog_import_test_fail()`); err != nil {
		t.Fatal("cannot install transaction rollback trigger")
	}
	defer db.ExecContext(ctx, "DROP TRIGGER IF EXISTS catalog_import_test_failure ON demo_catalog; DROP FUNCTION IF EXISTS catalog_import_test_fail()")
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
