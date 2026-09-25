package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"reflect"
	"testing"
)

func catalogSearchFixtures() []wine {
	return []wine{
		{ID: "search-rank-40-exact", Name: "Ёжевичный Резерв", Winery: "Шато", Year: 2021},
		{ID: "search-rank-50-exact", Name: "Ежевичный Резерв", Winery: "Шато", Year: 2021},
		{ID: "search-rank-20-partial", Name: "Ежевичный Резервный", Winery: "Шатонский", Year: 2021},
		{ID: "search-rank-10-typo", Name: "Еживичный Резерв", Winery: "Шато", Year: 2021},
	}
}

func wineIDs(items []wine) []string {
	ids := make([]string, len(items))
	for i := range items {
		ids[i] = items[i].ID
	}
	return ids
}

func TestCAT010NormalizesUnicodeAndRequiresEveryToken(t *testing.T) {
	items := []wine{{ID: "match", Name: "Ёжевичный Резерв", Winery: "Шато Север", Year: 2021}, {ID: "wrong-year", Name: "Ежевичный Резерв", Winery: "Шато Север", Year: 2020}}
	if got, want := wineIDs(rankWineList(items, "2021, шато! ЕЖЕВИЧНЫЙ")), []string{"match"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("normalized AND match=%v want=%v", got, want)
	}
	if got := rankWineList(items, "--- … !!!"); len(got) != 0 {
		t.Fatalf("punctuation-only query matched %v", wineIDs(got))
	}
	if got := rankWineList(items, "ежевичный шато 2021 мусор"); len(got) != 0 {
		t.Fatalf("unknown required token matched %v", wineIDs(got))
	}
}

func TestCAT011PrefixAndOneEditOnlyForAlphabeticWords(t *testing.T) {
	items := []wine{
		{ID: "prefix", Name: "Ежевичный Резерв", Winery: "Шато", Year: 2021},
		{ID: "substitution", Name: "Еживичный Резерв", Winery: "Шато", Year: 2021},
		{ID: "transpose", Name: "Ежевичынй Резерв", Winery: "Шато", Year: 2021},
		{ID: "short", Name: "Шато", Winery: "Дом", Year: 2021},
	}
	if got, want := wineIDs(rankWineList(items, "резе")), []string{"prefix", "substitution", "transpose"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("prefix match=%v want=%v", got, want)
	}
	if got := rankWineList(items, "вич"); len(got) != 0 {
		t.Fatalf("substring matched despite prefix-only behavior: %v", wineIDs(got))
	}
	if got, want := wineIDs(rankWineList(items, "еживичный")), []string{"substitution", "prefix"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("one substitution match=%v want=%v", got, want)
	}
	if got, want := wineIDs(rankWineList(items, "ежевичынй")), []string{"transpose", "prefix"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("adjacent transpose match=%v want=%v", got, want)
	}
	for _, query := range []string{"202", "2022", "шате"} {
		if got := rankWineList(items, query); len(got) != 0 {
			t.Fatalf("%q unexpectedly matched %v", query, wineIDs(got))
		}
	}
	for _, query := range []string{"ежвичный", "ежеваичный"} {
		if got, want := wineIDs(rankWineList([]wine{items[0]}, query)), []string{"prefix"}; !reflect.DeepEqual(got, want) {
			t.Fatalf("one insertion/deletion %q match=%v want=%v", query, got, want)
		}
	}
	if got := rankWineList([]wine{items[0]}, "ежвчный"); len(got) != 0 {
		t.Fatalf("two edits unexpectedly matched %v", wineIDs(got))
	}
}

func TestCAT012RanksExactBeforePrefixBeforeTypoWithIDTieBreak(t *testing.T) {
	query := "ежевичный резерв шато 2021"
	want := []string{"search-rank-40-exact", "search-rank-50-exact", "search-rank-20-partial", "search-rank-10-typo"}
	if got := wineIDs(rankWineList(catalogSearchFixtures(), query)); !reflect.DeepEqual(got, want) {
		t.Fatalf("ranked matches=%v want=%v", got, want)
	}
}

func TestCAT013RankedPaginationUsesCursorPositionAndGuards(t *testing.T) {
	query := "ежевичный резерв шато 2021"
	h := newHandlerWithCatalog("", nil, displayCatalog{version: "search-fixture-v1", items: catalogSearchFixtures()})
	first := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query), "")
	var page struct {
		Candidates []wine
		NextCursor string `json:"nextCursor"`
	}
	if err := json.NewDecoder(first.Body).Decode(&page); err != nil {
		t.Fatal(err)
	}
	if first.Code != http.StatusOK || page.NextCursor == "" {
		t.Fatalf("first status=%d page=%+v", first.Code, page)
	}
	if got, want := wineIDs(page.Candidates), []string{"search-rank-40-exact", "search-rank-50-exact"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("first IDs=%v want=%v", got, want)
	}
	second := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query)+"&cursor="+url.QueryEscape(page.NextCursor), "")
	var next struct {
		Candidates []wine
		NextCursor string `json:"nextCursor"`
	}
	if err := json.NewDecoder(second.Body).Decode(&next); err != nil {
		t.Fatal(err)
	}
	if second.Code != http.StatusOK || next.NextCursor != "" {
		t.Fatalf("second status=%d page=%+v", second.Code, next)
	}
	if got, want := wineIDs(next.Candidates), []string{"search-rank-20-partial", "search-rank-10-typo"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("second IDs=%v want=%v", got, want)
	}
	if changed := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query+" мусор")+"&cursor="+url.QueryEscape(page.NextCursor), ""); changed.Code != http.StatusBadRequest {
		t.Fatalf("changed query status=%d", changed.Code)
	}
	stale := encodeCatalogCursor("older-version", query, "search-rank-50-exact")
	if response := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query)+"&cursor="+url.QueryEscape(stale), ""); response.Code != http.StatusConflict {
		t.Fatalf("stale cursor status=%d", response.Code)
	}
	legacy := encodeLegacyTextCursor("search-fixture-v1", query, "search-rank-50-exact")
	if response := request(t, h, http.MethodGet, "/v2/catalog?limit=2&q="+url.QueryEscape(query)+"&cursor="+url.QueryEscape(legacy), ""); response.Code != http.StatusBadRequest {
		t.Fatalf("legacy text cursor status=%d", response.Code)
	}
	blank := newHandlerWithCatalog("", nil, displayCatalog{version: "search-fixture-v1", items: []wine{{ID: "b"}, {ID: "a"}}})
	legacyBlank := encodeLegacyTextCursor("search-fixture-v1", "", "a")
	response := request(t, blank, http.MethodGet, "/v2/catalog?limit=1&cursor="+url.QueryEscape(legacyBlank), "")
	var blankPage struct{ Candidates []wine }
	if err := json.NewDecoder(response.Body).Decode(&blankPage); err != nil {
		t.Fatal(err)
	}
	if response.Code != http.StatusOK || !reflect.DeepEqual(wineIDs(blankPage.Candidates), []string{"b"}) {
		t.Fatalf("legacy blank cursor status=%d page=%+v", response.Code, blankPage)
	}
}

func encodeLegacyTextCursor(version, query, id string) string {
	key := []byte("catalog-display-v2-cursor")
	sum := hmac.New(sha256.New, key)
	_, _ = sum.Write([]byte(version))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write([]byte(query))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write([]byte(id))
	raw, _ := json.Marshal(catalogCursor{Version: version, Query: query, ID: id, MAC: base64.RawURLEncoding.EncodeToString(sum.Sum(nil))})
	return base64.RawURLEncoding.EncodeToString(raw)
}

func TestCatalogSearchHonorsCancelledContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := rankWineListContext(ctx, catalogSearchFixtures(), "ежевичный"); err == nil {
		t.Fatal("cancelled matcher completed")
	}
}

func BenchmarkCatalogNameSearch2038(b *testing.B) {
	items := make([]wine, 2038)
	for i := range items {
		items[i] = wine{ID: fmt.Sprintf("synthetic-%04d", i), Name: "Синтетический Резерв", Winery: "Шато Проверка", Year: 2021}
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = rankWineList(items, "синтетический резерв шато 2021")
	}
}
