package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"testing"
)

type displayCatalog struct {
	items   []wine
	version string
}

func (s displayCatalog) List(context.Context) ([]wine, error) { return sortedWines(s.items), nil }
func (s displayCatalog) Search(_ context.Context, q *string) ([]wine, error) {
	return filterWineList(sortedWines(s.items), q), nil
}
func (s displayCatalog) CatalogInfo(context.Context) (catalogInfo, error) {
	return catalogInfo{Version: s.version}, nil
}
func (s displayCatalog) Resolve(_ context.Context, slug string) (wine, string, error) {
	if slug == "old-red" {
		slug = "red"
	}
	for _, item := range s.items {
		if item.ID == slug {
			return item, slug, nil
		}
	}
	return wine{}, "", errCatalogNotFound
}

func TestCAT001PaginationAndCAT002WholeCatalogQuery(t *testing.T) {
	store := displayCatalog{version: "2026-09", items: []wine{{ID: "z", Name: "Zulu"}, {ID: "red", Name: "Red", Winery: "North"}, {ID: "a", Name: "Amber"}}}
	h := newHandlerWithCatalog("", nil, store)
	first := request(t, h, http.MethodGet, "/v2/catalog?limit=1", "")
	var page struct {
		Demo           bool
		Candidates     []wine
		NextCursor     string `json:"nextCursor"`
		CatalogVersion string `json:"catalogVersion"`
	}
	if err := json.NewDecoder(first.Body).Decode(&page); err != nil {
		t.Fatal(err)
	}
	if first.Code != 200 || page.Demo || page.CatalogVersion != "2026-09" || len(page.Candidates) != 1 || page.Candidates[0].ID != "a" || page.NextCursor == "" {
		t.Fatalf("first page=%+v", page)
	}
	second := request(t, h, http.MethodGet, "/v2/catalog?limit=1&cursor="+page.NextCursor, "")
	var next struct{ Candidates []wine }
	_ = json.NewDecoder(second.Body).Decode(&next)
	if second.Code != 200 || len(next.Candidates) != 1 || next.Candidates[0].ID != "red" {
		t.Fatalf("second=%d %+v", second.Code, next)
	}
	query := request(t, h, http.MethodGet, "/v2/catalog?q=north", "")
	var searched struct{ Candidates []wine }
	_ = json.NewDecoder(query.Body).Decode(&searched)
	if query.Code != 200 || len(searched.Candidates) != 1 || searched.Candidates[0].ID != "red" {
		t.Fatalf("search=%d %+v", query.Code, searched)
	}
}
func TestCAT006AliasesAndCAT007Provenance(t *testing.T) {
	h := newHandlerWithCatalog("", nil, displayCatalog{version: "real-v1", items: []wine{{ID: "red", Name: "Red"}}})
	r := request(t, h, http.MethodGet, "/v2/catalog/old-red", "")
	var body struct {
		Demo           bool
		Candidate      wine
		CanonicalID    string `json:"canonicalId"`
		CatalogVersion string `json:"catalogVersion"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if r.Code != 200 || body.Demo || body.Candidate.ID != "red" || body.CanonicalID != "red" || body.CatalogVersion != "real-v1" {
		t.Fatalf("alias=%d %+v", r.Code, body)
	}
	missing := request(t, h, http.MethodGet, "/v2/catalog/nope", "")
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing=%d", missing.Code)
	}
}
func TestCAT001RejectsInvalidAndStaleCursor(t *testing.T) {
	store := displayCatalog{version: "one", items: []wine{{ID: "a"}, {ID: "b"}}}
	h := newHandlerWithCatalog("", nil, store)
	bad := request(t, h, http.MethodGet, "/v2/catalog?cursor=garbage", "")
	if bad.Code != 400 {
		t.Fatalf("bad=%d", bad.Code)
	}
	stale := encodeCatalogCursor("old", "", "a")
	old := request(t, h, http.MethodGet, "/v2/catalog?cursor="+stale, "")
	if old.Code != 409 {
		t.Fatalf("stale=%d", old.Code)
	}
}

func TestCAT001EmbeddedCatalogRejectsStaleCursor(t *testing.T) {
	h := newHandler(" ")
	stale := encodeCatalogCursor("old", "", "demo-cabernet-sauvignon-2023")
	if r := request(t, h, http.MethodGet, "/v2/catalog?cursor="+stale, ""); r.Code != http.StatusConflict {
		t.Fatalf("status=%d", r.Code)
	}
}

func TestCAT007KeepsSyntheticFixtureAssetPaths(t *testing.T) {
	if got := catalogAssetURL(defaultCatalogVersion, "/assets/catalog/demo.webp"); got != "/assets/catalog/demo.webp" {
		t.Fatalf("demo asset path=%q", got)
	}
	if got := catalogAssetURL("real-v1", "images/red.webp"); got != "/catalog-assets/real-v1/images/red.webp" {
		t.Fatalf("imported asset path=%q", got)
	}
}

func TestCAT001CompleteTraversalBoundsAndCAT002QueryBeyondFirstPage(t *testing.T) {
	items := make([]wine, 73)
	for i := range items {
		items[i] = wine{ID: fmt.Sprintf("wine-%03d", 72-i), Name: fmt.Sprintf("Wine %d", 72-i)}
	}
	h := newHandlerWithCatalog("", nil, displayCatalog{version: "fixture73", items: items})
	var got []string
	cursor := ""
	for pageNumber := 0; pageNumber < 4; pageNumber++ {
		path := "/v2/catalog"
		if cursor != "" {
			path += "?cursor=" + url.QueryEscape(cursor)
		}
		r := request(t, h, http.MethodGet, path, "")
		var p struct {
			Candidates []wine
			NextCursor string `json:"nextCursor"`
		}
		if r.Code != 200 {
			t.Fatalf("page status %d", r.Code)
		}
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
			t.Fatal(err)
		}
		if pageNumber == 0 && len(p.Candidates) != 24 {
			t.Fatal("default page must contain24")
		}
		for _, w := range p.Candidates {
			got = append(got, w.ID)
		}
		cursor = p.NextCursor
		if cursor == "" {
			break
		}
	}
	want := make([]string, 73)
	for i := range want {
		want[i] = fmt.Sprintf("wine-%03d", i)
	}
	if !reflect.DeepEqual(got, want) || cursor != "" {
		t.Fatalf("traversal lost/duplicated records: %v", got)
	}
	for _, limit := range []string{"0", "61", "bad"} {
		if r := request(t, h, "GET", "/v2/catalog?limit="+limit, ""); r.Code != 400 {
			t.Fatalf("limit%s status%d", limit, r.Code)
		}
	}
	r := request(t, h, "GET", "/v2/catalog?limit=60", "")
	var p struct{ Candidates []wine }
	_ = json.NewDecoder(r.Body).Decode(&p)
	if len(p.Candidates) != 60 {
		t.Fatal("maxpage")
	}
	r = request(t, h, "GET", "/v2/catalog?q=Wine%2072", "")
	_ = json.NewDecoder(r.Body).Decode(&p)
	if len(p.Candidates) != 1 || p.Candidates[0].ID != "wine-072" {
		t.Fatal("query only searched initial page")
	}
	token := encodeCatalogCursor("fixture73", "Wine", "wine-001")
	if r := request(t, h, "GET", "/v2/catalog?q=Other&cursor="+url.QueryEscape(token), ""); r.Code != 400 {
		t.Fatal("cursor reused for anotherquery")
	}
	if r := request(t, h, "GET", "/v2/catalog?q="+strings.Repeat("я", 257), ""); r.Code != 400 {
		t.Fatal("unbounded query accepted")
	}
}
