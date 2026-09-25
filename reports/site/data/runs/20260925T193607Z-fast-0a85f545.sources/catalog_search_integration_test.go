//go:build integration

package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"os"
	"reflect"
	"testing"
)

func TestCAT014PostgresHTTPUsesSharedRankedPaging(t *testing.T) {
	prepareDatabase(t)
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal("migration database unavailable")
	}
	defer db.Close()
	fixtures := []wine{
		{ID: "cat014-rank-40-exact", Slug: "cat014-rank-40-exact", Name: "Ёжевичный Резерв", Winery: "Шато", Year: 2021, Description: "full metadata 40"},
		{ID: "cat014-rank-50-exact", Slug: "cat014-rank-50-exact", Name: "Ежевичный Резерв", Winery: "Шато", Year: 2021, Description: "full metadata 50"},
		{ID: "cat014-rank-20-partial", Slug: "cat014-rank-20-partial", Name: "Ежевичный Резервный", Winery: "Шатонский", Year: 2021, Description: "full metadata 20"},
		{ID: "cat014-rank-10-typo", Slug: "cat014-rank-10-typo", Name: "Еживичный Резерв", Winery: "Шато", Year: 2021, Description: "full metadata 10"},
	}
	for index, item := range fixtures {
		if _, err := db.ExecContext(context.Background(), `INSERT INTO catalog_items(id, slug, name, winery, year, image, description, metadata, display_order) VALUES($1, $2, $3, $4, $5, '', $6, '{}'::jsonb, $7)`, item.ID, item.Slug, item.Name, item.Winery, item.Year, item.Description, 30000+index); err != nil {
			t.Fatal(err)
		}
	}
	// This record participates in the lightweight rank scan but never matches
	// the query. Its bad full projection proves the page does not hydrate every
	// catalog row before selecting its IDs.
	const poisonID = "cat014-unmatched-poison"
	if _, err := db.ExecContext(context.Background(), `INSERT INTO catalog_items(id, slug, name, winery, year, image, description, metadata, display_order) VALUES($1, $1, 'Неподходящее', 'Другое', 2021, '', '', '{"year":"invalid"}'::jsonb, 30010)`, poisonID); err != nil {
		t.Fatal(err)
	}
	defer func() {
		if _, err := db.ExecContext(context.Background(), "DELETE FROM catalog_items WHERE id=$1", poisonID); err != nil {
			t.Errorf("remove CAT014 poison fixture: %v", err)
		}
		for _, item := range fixtures {
			if _, err := db.ExecContext(context.Background(), "DELETE FROM catalog_items WHERE id=$1", item.ID); err != nil {
				t.Errorf("remove CAT014 fixture %s: %v", item.ID, err)
			}
		}
	}()

	store, closeStore := realCatalog(t)
	defer closeStore()
	h := newHandlerWithCatalog("", nil, store)
	query := "ежевичный резерв шато 2021"
	first := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query), "")
	var firstPage struct {
		Candidates []wine
		NextCursor string `json:"nextCursor"`
	}
	if err := json.NewDecoder(first.Body).Decode(&firstPage); err != nil {
		t.Fatal(err)
	}
	if first.Code != http.StatusOK || firstPage.NextCursor == "" || !reflect.DeepEqual(wineIDs(firstPage.Candidates), []string{"cat014-rank-40-exact", "cat014-rank-50-exact"}) || firstPage.Candidates[0].Description != "full metadata 40" {
		t.Fatalf("first PostgreSQL page status=%d page=%+v", first.Code, firstPage)
	}
	second := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query)+"&cursor="+url.QueryEscape(firstPage.NextCursor), "")
	var secondPage struct {
		Candidates []wine
		NextCursor string `json:"nextCursor"`
	}
	if err := json.NewDecoder(second.Body).Decode(&secondPage); err != nil {
		t.Fatal(err)
	}
	if second.Code != http.StatusOK || secondPage.NextCursor != "" || !reflect.DeepEqual(wineIDs(secondPage.Candidates), []string{"cat014-rank-20-partial", "cat014-rank-10-typo"}) {
		t.Fatalf("second PostgreSQL page status=%d page=%+v", second.Code, secondPage)
	}
	if changed := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query+" мусор")+"&cursor="+url.QueryEscape(firstPage.NextCursor), ""); changed.Code != http.StatusBadRequest {
		t.Fatalf("changed query status=%d", changed.Code)
	}
	stale := encodeCatalogCursor("obsolete-version", query, "cat014-rank-50-exact")
	if response := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query)+"&cursor="+url.QueryEscape(stale), ""); response.Code != http.StatusConflict {
		t.Fatalf("stale cursor status=%d", response.Code)
	}
}
