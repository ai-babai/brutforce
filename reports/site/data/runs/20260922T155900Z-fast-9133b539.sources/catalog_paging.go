package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"
)

const defaultCatalogPageSize = 24

type catalogCursor struct {
	Version string `json:"v"`
	Query   string `json:"q"`
	ID      string `json:"i"`
	MAC     string `json:"m"`
}
type catalogHTTPPage struct {
	candidates          []wine
	nextCursor, version string
	demo                bool
	err                 error
}

func catalogPageForRequest(r *http.Request, store catalogReader) (catalogHTTPPage, int, string, string) {
	limit := defaultCatalogPageSize
	if raw := r.URL.Query().Get("limit"); raw != "" {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 || value > 60 {
			return catalogHTTPPage{}, 400, "invalid_limit", "limit must be an integer from 1 to 60"
		}
		limit = value
	}
	query := strings.TrimSpace(r.URL.Query().Get("q"))
	if !utf8.ValidString(query) || utf8.RuneCountInString(query) > 256 {
		return catalogHTTPPage{}, 400, "invalid_query", "query must contain at most256 characters"
	}
	after := ""
	expectedVersion := ""
	if raw := r.URL.Query().Get("cursor"); raw != "" {
		cursor, ok := decodeCatalogCursor(raw)
		if !ok || cursor.Query != query {
			return catalogHTTPPage{}, 400, "invalid_cursor", "cursor is invalid"
		}
		after = cursor.ID
		expectedVersion = cursor.Version
	}
	if pager, ok := store.(catalogPager); ok {
		page, err := pager.Page(r.Context(), catalogPageRequest{Query: query, AfterID: after, ExpectedVersion: expectedVersion, Limit: limit})
		if err != nil {
			if errors.Is(err, errCatalogStaleCursor) {
				return catalogHTTPPage{}, 409, "stale_cursor", "cursor belongs to an older catalog version"
			}
			return catalogHTTPPage{err: err}, 0, "", ""
		}
		info := page.Info
		result := catalogHTTPPage{candidates: page.Candidates, version: info.Version, demo: info.Demo}
		if page.HasMore && len(page.Candidates) > 0 {
			result.nextCursor = encodeCatalogCursor(info.Version, query, page.Candidates[len(page.Candidates)-1].ID)
		}
		return result, 0, "", ""
	}
	info, err := catalogInfoFor(r.Context(), store)
	if err != nil {
		return catalogHTTPPage{err: err}, 0, "", ""
	}
	if expectedVersion != "" && expectedVersion != info.Version {
		return catalogHTTPPage{}, 409, "stale_cursor", "cursor belongs to an older catalog version"
	}
	items, err := store.Search(r.Context(), stringPtr(query))
	if err != nil {
		return catalogHTTPPage{err: err}, 0, "", ""
	}
	items = sortedWines(items)
	page := pageWineSlice(items, catalogPageRequest{AfterID: after, Limit: limit})
	result := catalogHTTPPage{candidates: page.Candidates, version: info.Version, demo: info.Demo}
	if page.HasMore && len(page.Candidates) > 0 {
		result.nextCursor = encodeCatalogCursor(info.Version, query, page.Candidates[len(page.Candidates)-1].ID)
	}
	return result, 0, "", ""
}
func encodeCatalogCursor(version, query, id string) string {
	c := catalogCursor{Version: version, Query: query, ID: id}
	c.MAC = cursorMAC(c.Version, c.Query, c.ID)
	raw, _ := json.Marshal(c)
	return base64.RawURLEncoding.EncodeToString(raw)
}
func decodeCatalogCursor(raw string) (catalogCursor, bool) {
	data, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return catalogCursor{}, false
	}
	var c catalogCursor
	if json.Unmarshal(data, &c) != nil || c.Version == "" || c.ID == "" || !hmac.Equal([]byte(c.MAC), []byte(cursorMAC(c.Version, c.Query, c.ID))) {
		return catalogCursor{}, false
	}
	return c, true
}
func cursorMAC(version, query, id string) string {
	key := []byte("catalog-display-v2-cursor")
	sum := hmac.New(sha256.New, key)
	_, _ = sum.Write([]byte(version))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write([]byte(query))
	_, _ = sum.Write([]byte{0})
	_, _ = sum.Write([]byte(id))
	return base64.RawURLEncoding.EncodeToString(sum.Sum(nil))
}
