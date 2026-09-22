package catalogimport

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
)

const tinyWebP = "UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEAAUAmJaQAA3AA/v3AgAA="
const tinyWebPSHA = "2c8e008a6a06d559032d6fa985a99d83cac9fe1ddbe8512f98620e70ab3ebd0b"

func writePackage(t *testing.T, wines, aliases string) string {
	t.Helper()
	root := t.TempDir()
	public := filepath.Join(root, "public")
	if err := os.MkdirAll(filepath.Join(public, "images"), 0755); err != nil {
		t.Fatal(err)
	}
	image, _ := base64.StdEncoding.DecodeString(tinyWebP)
	if err := os.WriteFile(filepath.Join(public, "images", "wine.webp"), image, 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(public, "wines.json"), []byte(wines), 0644); err != nil {
		t.Fatal(err)
	}
	if aliases != "" {
		if err := os.WriteFile(filepath.Join(public, "aliases.json"), []byte(aliases), 0644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}
func wineJSON(extra string) string {
	return fmt.Sprintf(`[{"slug":"synthetic-wine","title":"Synthetic Wine","producer":"Test Cellar","vintage_year":2024,"source_url":"https://example.test/wine","image":{"path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44,"variants":[{"role":"thumbnail","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"card","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"original","path":"images/wine.webp","sha256":"%s","mime_type":"image/webp","width":1,"height":1,"bytes":44}]},%s}]`, tinyWebPSHA, tinyWebPSHA, tinyWebPSHA, tinyWebPSHA, extra)
}

func TestCAT008LoadValidatesPackageAndKeepsTypedProjection(t *testing.T) {
	root := writePackage(t, wineJSON(`"website_details":{"leak":"must not be projected"},"alcohol_percent":135,"volume_l":0.75`), `{"aliases":[{"alias_slug":"former-synthetic-wine","canonical_slug":"synthetic-wine"}]}`)
	wines, aliases, err := Load(root, "public-v2")
	if err != nil {
		t.Fatal(err)
	}
	if len(wines) != 1 || wines[0].Year != 2024 || wines[0].AlcoholPercent != nil || wines[0].Image != "images/wine.webp" {
		t.Fatalf("unexpected projection: %#v", wines)
	}
	if len(wines[0].ImageVariants) != 3 || len(aliases) != 1 {
		t.Fatal("variants or aliases were not imported")
	}
	if raw := fmt.Sprintf("%#v", wines[0]); strings.Contains(raw, "website_details") || strings.Contains(raw, "must not be projected") {
		t.Fatal("raw source fields leaked into display projection")
	}
}
func TestCAT008RejectsTraversalChecksumAndAliasConflicts(t *testing.T) {
	for name, test := range map[string]struct{ wine, aliases string }{
		"traversal":       {strings.Replace(wineJSON(`"x":"y"`), "images/wine.webp", "../outside.webp", 1), ""},
		"checksum":        {strings.Replace(wineJSON(`"x":"y"`), tinyWebPSHA, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 1), ""},
		"alias target":    {wineJSON(`"x":"y"`), `{"aliases":[{"alias_slug":"old","canonical_slug":"missing"}]}`},
		"alias collision": {wineJSON(`"x":"y"`), `{"aliases":[{"alias_slug":"synthetic-wine","canonical_slug":"synthetic-wine"}]}`},
		"source URL":      {strings.Replace(wineJSON(`"x":"y"`), "https://example.test/wine", "javascript:alert(1)", 1), ""},
	} {
		t.Run(name, func(t *testing.T) {
			root := writePackage(t, test.wine, test.aliases)
			if _, _, err := Load(root, "v2"); err == nil {
				t.Fatal("expected validation failure")
			}
		})
	}
}
func TestCAT008RejectsSymlinkedAssets(t *testing.T) {
	root := writePackage(t, wineJSON(`"x":"y"`), "")
	public := filepath.Join(root, "public")
	image, _ := base64.StdEncoding.DecodeString(tinyWebP)
	if err := os.WriteFile(filepath.Join(root, "elsewhere.webp"), image, 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(public, "images", "wine.webp")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(root, "elsewhere.webp"), filepath.Join(public, "images", "wine.webp")); err != nil {
		t.Skip("symlink unavailable")
	}
	if _, _, err := Load(root, "v2"); err == nil {
		t.Fatal("symlink must be rejected")
	}
	root = writePackage(t, wineJSON(`"x":"y"`), "")
	public = filepath.Join(root, "public")
	if err := os.Rename(filepath.Join(public, "images"), filepath.Join(root, "outside-images")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(root, "outside-images"), filepath.Join(public, "images")); err != nil {
		t.Skip("symlink unavailable")
	}
	if _, _, err := Load(root, "v2"); err == nil {
		t.Fatal("symlinked image directory must be rejected")
	}
}

func TestCAT008RejectsNonNullImageWithoutPaths(t *testing.T) {
	for name, wine := range map[string]string{
		"missing master path":  strings.Replace(wineJSON(`"x":"y"`), `"path":"images/wine.webp"`, `"path":""`, 1),
		"missing variant path": strings.Replace(wineJSON(`"x":"y"`), `"role":"thumbnail","path":"images/wine.webp"`, `"role":"thumbnail","path":""`, 1),
		"absent image field":   strings.Replace(wineJSON(`"x":"y"`), `"image":{"path":"images/wine.webp","sha256":"`+tinyWebPSHA+`","mime_type":"image/webp","width":1,"height":1,"bytes":44,"variants":[{"role":"thumbnail","path":"images/wine.webp","sha256":"`+tinyWebPSHA+`","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"card","path":"images/wine.webp","sha256":"`+tinyWebPSHA+`","mime_type":"image/webp","width":1,"height":1,"bytes":44},{"role":"original","path":"images/wine.webp","sha256":"`+tinyWebPSHA+`","mime_type":"image/webp","width":1,"height":1,"bytes":44}]}`, ``, 1),
	} {
		t.Run(name, func(t *testing.T) {
			root := writePackage(t, wine, "")
			if _, _, err := Load(root, "v2"); err == nil {
				t.Fatal("expected image validation failure")
			}
		})
	}
}

func TestCAT008ProjectsOnlyContractFields(t *testing.T) {
	tests := []struct {
		name, extra string
		check       func(*testing.T, catalogmodel.Wine)
	}{
		{"provenance and geography", `"source_snapshot_date":"2026-09-01","region":["Kuban"],"grapes":["Merlot"],"category_and_sweetness":"red dry"`, func(t *testing.T, w catalogmodel.Wine) {
			if w.SourceSnapshotDate != "2026-09-01" || !reflect.DeepEqual(w.Region, []string{"Kuban"}) || !reflect.DeepEqual(w.Grapes, []string{"Merlot"}) || w.CategoryAndSweetness != "red dry" {
				t.Fatalf("projection=%#v", w)
			}
		}},
		{"valid ABV and volume", `"alcohol_percent":12.5,"alcohol_min_percent":11.5,"alcohol_max_percent":13.5,"volume_l":0.75`, func(t *testing.T, w catalogmodel.Wine) {
			if w.AlcoholPercent == nil || *w.AlcoholPercent != 12.5 || w.AlcoholMinPercent == nil || *w.AlcoholMinPercent != 11.5 || w.AlcoholMaxPercent == nil || *w.AlcoholMaxPercent != 13.5 || w.VolumeL == nil || *w.VolumeL != 0.75 {
				t.Fatalf("ABV projection=%#v", w)
			}
		}},
		{"unmodelled source detail dropped", `"website_details":{"address":"private-source-only"},"legacy_score":99`, func(t *testing.T, w catalogmodel.Wine) {
			if raw := fmt.Sprintf("%#v", w); strings.Contains(raw, "private-source-only") || strings.Contains(raw, "legacy_score") {
				t.Fatalf("unmodelled data leaked: %s", raw)
			}
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := writePackage(t, wineJSON(test.extra), "")
			wines, _, err := Load(root, "v2")
			if err != nil {
				t.Fatal(err)
			}
			test.check(t, wines[0])
		})
	}
}

func TestMetadataExcludesCanonicalColumns(t *testing.T) {
	raw, err := metadata(catalogmodel.Wine{ID: "stable-id", Slug: "public-slug", Name: "Wine", Winery: "Cellar", Year: 2024, Image: "image.webp", Description: "Description", Region: []string{"Kuban"}})
	if err != nil {
		t.Fatal(err)
	}
	var got map[string]any
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"id", "slug", "name", "winery", "year", "image", "description"} {
		if _, exists := got[key]; exists {
			t.Fatalf("canonical column %q duplicated in metadata", key)
		}
	}
	if _, exists := got["region"]; !exists {
		t.Fatal("extended projection missing from metadata")
	}
}

func TestContentAddressedMediaKeyRequiresMatchingHexDigest(t *testing.T) {
	sha := strings.Repeat("a", 64)
	if !validMediaKey("400/"+sha+".webp", sha) {
		t.Fatal("valid content-addressed key rejected")
	}
	for _, key := range []string{
		"400/" + strings.Repeat("g", 64) + ".webp",
		"400/" + strings.Repeat("b", 64) + ".webp",
		"400/" + strings.Repeat("A", 64) + ".webp",
		"400/" + sha + ".png",
	} {
		if validMediaKey(key, sha) {
			t.Fatalf("invalid content-addressed key accepted: %s", key)
		}
	}
}
