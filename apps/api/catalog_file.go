package main

import (
	"context"
	"encoding/json"
	"os"
)

// The stand keeps the production display projection, not the eight demo fixtures.
type fileCatalogStore struct {
	Version string            `json:"version"`
	Wines   []wine            `json:"wines"`
	Aliases map[string]string `json:"aliases"`
}

func demoStandEnabled() bool { return os.Getenv("DEMO_STAND_CATALOG_FILE") != "" }

func openFileCatalog(path string) (catalogReader, func(), error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, errCatalogUnavailable
	}
	var store fileCatalogStore
	if json.Unmarshal(data, &store) != nil || store.Version == "" || len(store.Wines) == 0 {
		return nil, nil, errCatalogUnavailable
	}
	store.Wines = sortedWines(store.Wines)
	return &store, func() {}, nil
}

func (s *fileCatalogStore) CatalogInfo(context.Context) (catalogInfo, error) {
	return catalogInfo{Version: s.Version, Demo: false}, nil
}
func (s *fileCatalogStore) HasCatalogVersion(_ context.Context, version string) (bool, error) {
	return version == s.Version, nil
}
func (s *fileCatalogStore) List(context.Context) ([]wine, error) {
	return append([]wine(nil), s.Wines...), nil
}
func (s *fileCatalogStore) Search(_ context.Context, query *string) ([]wine, error) {
	return filterWineList(s.Wines, query), nil
}
func (s *fileCatalogStore) Page(_ context.Context, req catalogPageRequest) (catalogPage, error) {
	if req.ExpectedVersion != "" && req.ExpectedVersion != s.Version {
		return catalogPage{}, errCatalogStaleCursor
	}
	page := pageWineSlice(rankWineList(s.Wines, req.Query), req)
	page.Info = catalogInfo{Version: s.Version, Demo: false}
	if page.Candidates == nil {
		page.Candidates = []wine{}
	}
	return page, nil
}
func (s *fileCatalogStore) ResolveDetail(_ context.Context, slug string) (wine, string, catalogInfo, error) {
	if canonical, ok := s.Aliases[slug]; ok {
		slug = canonical
	}
	info := catalogInfo{Version: s.Version, Demo: false}
	for _, item := range s.Wines {
		if item.Slug == slug || item.ID == slug {
			return item, item.Slug, info, nil
		}
	}
	return wine{}, "", info, errCatalogNotFound
}
func (s *fileCatalogStore) ResolveIDDetail(_ context.Context, id string) (wine, catalogInfo, error) {
	info := catalogInfo{Version: s.Version, Demo: false}
	for _, item := range s.Wines {
		if item.ID == id {
			return item, info, nil
		}
	}
	return wine{}, info, errCatalogNotFound
}
