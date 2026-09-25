package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const catalogQueryTimeout = 2 * time.Second

var (
	errCatalogUnavailable = errors.New("catalog unavailable")
	errCatalogNotFound    = errors.New("catalog item not found")
	errCatalogStaleCursor = errors.New("catalog cursor is stale")
)

type catalogReader interface {
	List(context.Context) ([]wine, error)
	Search(context.Context, *string) ([]wine, error)
}
type catalogInfo struct {
	Version string
	Demo    bool
}
type catalogPageRequest struct {
	Query, AfterID, ExpectedVersion string
	Limit                           int
}
type catalogPage struct {
	Candidates []wine
	HasMore    bool
	Info       catalogInfo
}
type catalogPager interface {
	Page(context.Context, catalogPageRequest) (catalogPage, error)
}
type catalogResolver interface {
	Resolve(context.Context, string) (wine, string, error)
}
type catalogDetailResolver interface {
	ResolveDetail(context.Context, string) (wine, string, catalogInfo, error)
}
type catalogIDResolver interface {
	ResolveIDDetail(context.Context, string) (wine, catalogInfo, error)
}
type catalogVersionRegistry interface {
	HasCatalogVersion(context.Context, string) (bool, error)
}
type catalogInformer interface {
	CatalogInfo(context.Context) (catalogInfo, error)
}

type embeddedCatalogStore struct{}

func (embeddedCatalogStore) List(context.Context) ([]wine, error) { return sortedWines(demoWines), nil }
func (embeddedCatalogStore) Search(_ context.Context, q *string) ([]wine, error) {
	return filterWineList(demoWines, q), nil
}
func (embeddedCatalogStore) CatalogInfo(context.Context) (catalogInfo, error) {
	return catalogInfo{Version: defaultCatalogVersion, Demo: true}, nil
}
func (embeddedCatalogStore) HasCatalogVersion(context.Context, string) (bool, error) {
	return false, nil
}
func (embeddedCatalogStore) Page(_ context.Context, req catalogPageRequest) (catalogPage, error) {
	if req.ExpectedVersion != "" && req.ExpectedVersion != defaultCatalogVersion {
		return catalogPage{}, errCatalogStaleCursor
	}
	return pageWineSlice(rankWineList(demoWines, req.Query), req), nil
}
func (embeddedCatalogStore) Resolve(_ context.Context, slug string) (wine, string, error) {
	for _, item := range demoWines {
		if item.ID == slug {
			return item, item.ID, nil
		}
	}
	return wine{}, "", errCatalogNotFound
}
func (embeddedCatalogStore) ResolveIDDetail(_ context.Context, id string) (wine, catalogInfo, error) {
	for _, item := range demoWines {
		if item.ID == id {
			return item, catalogInfo{Version: defaultCatalogVersion, Demo: true}, nil
		}
	}
	return wine{}, catalogInfo{Version: defaultCatalogVersion, Demo: true}, errCatalogNotFound
}

type postgresCatalogStore struct{ pool *pgxpool.Pool }

func openConfiguredCatalog(ctx context.Context) (catalogReader, func(), error) {
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		return embeddedCatalogStore{}, func() {}, nil
	}
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, nil, errCatalogUnavailable
	}
	config.MaxConns, config.MinConns, config.MaxConnLifetime = 4, 0, 5*time.Minute
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, nil, errCatalogUnavailable
	}
	pingCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, nil, errCatalogUnavailable
	}
	return postgresCatalogStore{pool}, pool.Close, nil
}
func (s postgresCatalogStore) CatalogInfo(ctx context.Context) (catalogInfo, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	var version string
	err := s.pool.QueryRow(queryCtx, "SELECT version FROM catalog_state WHERE singleton = TRUE").Scan(&version)
	if errors.Is(err, pgx.ErrNoRows) {
		return catalogInfo{Version: defaultCatalogVersion, Demo: true}, nil
	}
	if err != nil || version == "" {
		return catalogInfo{}, errCatalogUnavailable
	}
	return catalogInfo{Version: version, Demo: version == defaultCatalogVersion}, nil
}
func (s postgresCatalogStore) HasCatalogVersion(ctx context.Context, version string) (bool, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	var found bool
	if err := s.pool.QueryRow(queryCtx, "SELECT EXISTS(SELECT 1 FROM catalog_versions WHERE version=$1)", version).Scan(&found); err != nil {
		return false, errCatalogUnavailable
	}
	return found, nil
}
func (s postgresCatalogStore) List(ctx context.Context) ([]wine, error) {
	info, err := s.CatalogInfo(ctx)
	if err != nil {
		return nil, err
	}
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	rows, err := s.pool.Query(queryCtx, "SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items ORDER BY display_order")
	if err != nil {
		return nil, errCatalogUnavailable
	}
	defer rows.Close()
	return scanWines(rows, info.Version)
}
func (s postgresCatalogStore) Search(ctx context.Context, query *string) ([]wine, error) {
	items, err := s.List(ctx)
	if err != nil {
		return nil, err
	}
	return filterWineList(items, query), nil
}
func (s postgresCatalogStore) Page(ctx context.Context, req catalogPageRequest) (catalogPage, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	tx, err := s.pool.BeginTx(queryCtx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead})
	if err != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	defer tx.Rollback(queryCtx)
	info, err := catalogInfoTx(queryCtx, tx)
	if err != nil {
		return catalogPage{}, err
	}
	if req.ExpectedVersion != "" && req.ExpectedVersion != info.Version {
		return catalogPage{}, errCatalogStaleCursor
	}
	if parseCatalogSearchQuery(req.Query).blank {
		rows, err := tx.Query(queryCtx, `SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items WHERE ($1 = '' OR id > $1) ORDER BY id LIMIT $2`, req.AfterID, req.Limit+1)
		if err != nil {
			return catalogPage{}, errCatalogUnavailable
		}
		defer rows.Close()
		items, err := scanWines(rows, info.Version)
		if err != nil {
			return catalogPage{}, err
		}
		if err := tx.Commit(queryCtx); err != nil {
			return catalogPage{}, errCatalogUnavailable
		}
		return catalogPage{Candidates: items[:min(len(items), req.Limit)], HasMore: len(items) > req.Limit, Info: info}, nil
	}
	// Text search ranks in Go so embedded, fallback HTTP, and PostgreSQL share
	// the same Unicode and typo semantics. Fetch only ranking fields first.
	rows, err := tx.Query(queryCtx, `SELECT id, name, winery, year FROM catalog_items`)
	if err != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	defer rows.Close()
	rankingRows := make([]wine, 0, 2048)
	for rows.Next() {
		var item wine
		var year *int
		if err := rows.Scan(&item.ID, &item.Name, &item.Winery, &year); err != nil {
			return catalogPage{}, errCatalogUnavailable
		}
		if year != nil {
			item.Year = *year
		}
		rankingRows = append(rankingRows, item)
	}
	if rows.Err() != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	ranked, err := rankWineListContext(queryCtx, rankingRows, req.Query)
	if err != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	page := pageWineSlice(ranked, req)
	if len(page.Candidates) == 0 {
		if err := tx.Commit(queryCtx); err != nil {
			return catalogPage{}, errCatalogUnavailable
		}
		page.Info = info
		return page, nil
	}
	ids := make([]string, len(page.Candidates))
	for i := range page.Candidates {
		ids[i] = page.Candidates[i].ID
	}
	rows.Close()
	rows, err = tx.Query(queryCtx, `SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items WHERE id = ANY($1)`, ids)
	if err != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	defer rows.Close()
	items, err := scanWines(rows, info.Version)
	if err != nil {
		return catalogPage{}, err
	}
	byID := make(map[string]wine, len(items))
	for _, item := range items {
		byID[item.ID] = item
	}
	items = make([]wine, 0, len(ids))
	for _, id := range ids {
		item, ok := byID[id]
		if !ok {
			return catalogPage{}, errCatalogUnavailable
		}
		items = append(items, item)
	}
	if err := tx.Commit(queryCtx); err != nil {
		return catalogPage{}, errCatalogUnavailable
	}
	page.Candidates, page.Info = items, info
	return page, nil
}
func (s postgresCatalogStore) Resolve(ctx context.Context, slug string) (wine, string, error) {
	item, canonical, _, err := s.ResolveDetail(ctx, slug)
	return item, canonical, err
}
func (s postgresCatalogStore) ResolveDetail(ctx context.Context, slug string) (wine, string, catalogInfo, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	tx, err := s.pool.BeginTx(queryCtx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead})
	if err != nil {
		return wine{}, "", catalogInfo{}, errCatalogUnavailable
	}
	defer tx.Rollback(queryCtx)
	info, err := catalogInfoTx(queryCtx, tx)
	if err != nil {
		return wine{}, "", catalogInfo{}, err
	}
	var canonical string
	if err := tx.QueryRow(queryCtx, "SELECT COALESCE((SELECT canonical_slug FROM catalog_aliases WHERE alias_slug=$1), $1)", slug).Scan(&canonical); err != nil {
		return wine{}, "", catalogInfo{}, errCatalogUnavailable
	}
	rows, err := tx.Query(queryCtx, "SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items WHERE slug=$1", canonical)
	if err != nil {
		return wine{}, "", catalogInfo{}, errCatalogUnavailable
	}
	defer rows.Close()
	items, err := scanWines(rows, info.Version)
	if err != nil {
		return wine{}, "", catalogInfo{}, err
	}
	if len(items) != 1 {
		return wine{}, "", info, errCatalogNotFound
	}
	if err := tx.Commit(queryCtx); err != nil {
		return wine{}, "", catalogInfo{}, errCatalogUnavailable
	}
	return items[0], canonical, info, nil
}

func (s postgresCatalogStore) ResolveIDDetail(ctx context.Context, id string) (wine, catalogInfo, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	tx, err := s.pool.BeginTx(queryCtx, pgx.TxOptions{IsoLevel: pgx.RepeatableRead})
	if err != nil {
		return wine{}, catalogInfo{}, errCatalogUnavailable
	}
	defer tx.Rollback(queryCtx)
	info, err := catalogInfoTx(queryCtx, tx)
	if err != nil {
		return wine{}, catalogInfo{}, err
	}
	rows, err := tx.Query(queryCtx, "SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items WHERE id=$1", id)
	if err != nil {
		return wine{}, catalogInfo{}, errCatalogUnavailable
	}
	defer rows.Close()
	items, err := scanWines(rows, info.Version)
	if err != nil {
		return wine{}, catalogInfo{}, err
	}
	if len(items) != 1 {
		return wine{}, info, errCatalogNotFound
	}
	if err := tx.Commit(queryCtx); err != nil {
		return wine{}, catalogInfo{}, errCatalogUnavailable
	}
	return items[0], info, nil
}

func catalogInfoTx(ctx context.Context, tx pgx.Tx) (catalogInfo, error) {
	var version string
	err := tx.QueryRow(ctx, "SELECT version FROM catalog_state WHERE singleton = TRUE").Scan(&version)
	if errors.Is(err, pgx.ErrNoRows) {
		return catalogInfo{Version: defaultCatalogVersion, Demo: true}, nil
	}
	if err != nil || version == "" {
		return catalogInfo{}, errCatalogUnavailable
	}
	return catalogInfo{Version: version, Demo: version == defaultCatalogVersion}, nil
}
func scanWines(rows pgx.Rows, version string) ([]wine, error) {
	result := make([]wine, 0, 8)
	for rows.Next() {
		var item wine
		var year *int
		var metadata []byte
		if err := rows.Scan(&item.ID, &item.Slug, &item.Name, &item.Winery, &year, &item.Image, &item.Description, &metadata); err != nil {
			return nil, errCatalogUnavailable
		}
		if year != nil {
			item.Year = *year
		}
		if len(metadata) > 0 && string(metadata) != "null" {
			if json.Unmarshal(metadata, &item) != nil {
				return nil, errCatalogUnavailable
			}
		}
		item.Image = catalogAssetURL(version, item.Image)
		for i := range item.ImageVariants {
			item.ImageVariants[i].Path = catalogAssetURL(version, item.ImageVariants[i].Path)
		}
		result = append(result, item)
	}
	if rows.Err() != nil {
		return nil, errCatalogUnavailable
	}
	return result, nil
}
func catalogAssetURL(version, value string) string {
	if value == "" || strings.Contains(value, "://") {
		return ""
	}
	// The embedded/seeded demo keeps its established public fixture paths.
	// Imported catalog packages always use the versioned immutable asset root.
	if version == defaultCatalogVersion && strings.HasPrefix(value, "/assets/") {
		return value
	}
	path := strings.TrimPrefix(value, "/")
	if path == "" || strings.HasPrefix(path, "../") || strings.Contains(path, "/../") {
		return ""
	}
	return "/media/catalog/" + path
}
func catalogInfoFor(ctx context.Context, store catalogReader) (catalogInfo, error) {
	if x, ok := store.(catalogInformer); ok {
		return x.CatalogInfo(ctx)
	}
	return catalogInfo{Version: defaultCatalogVersion, Demo: true}, nil
}
func catalogLookup(ctx context.Context, store catalogReader, slug string) (wine, string, catalogInfo, error) {
	if resolver, ok := store.(catalogDetailResolver); ok {
		return resolver.ResolveDetail(ctx, slug)
	}
	info, err := catalogInfoFor(ctx, store)
	if err != nil {
		return wine{}, "", catalogInfo{}, err
	}
	if x, ok := store.(catalogResolver); ok {
		item, canonical, err := x.Resolve(ctx, slug)
		return item, canonical, info, err
	}
	items, err := store.List(ctx)
	if err != nil {
		return wine{}, "", info, err
	}
	for _, item := range items {
		if item.ID == slug {
			return item, item.ID, info, nil
		}
	}
	return wine{}, "", info, errCatalogNotFound
}

func catalogLookupByID(ctx context.Context, store catalogReader, id string) (wine, catalogInfo, error) {
	if resolver, ok := store.(catalogIDResolver); ok {
		return resolver.ResolveIDDetail(ctx, id)
	}
	info, err := catalogInfoFor(ctx, store)
	if err != nil {
		return wine{}, catalogInfo{}, err
	}
	items, err := store.List(ctx)
	if err != nil {
		return wine{}, info, err
	}
	for _, item := range items {
		if item.ID == id {
			return item, info, nil
		}
	}
	return wine{}, info, errCatalogNotFound
}
func filterWineList(catalog []wine, query *string) []wine {
	if query == nil {
		return append([]wine(nil), catalog...)
	}
	return rankWineList(catalog, *query)
}
func sortedWines(in []wine) []wine {
	out := append([]wine(nil), in...)
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}
func pageWineSlice(items []wine, req catalogPageRequest) catalogPage {
	start := 0
	if req.AfterID != "" {
		for start < len(items) && items[start].ID != req.AfterID {
			start++
		}
		if start == len(items) {
			return catalogPage{Info: catalogInfo{Version: defaultCatalogVersion, Demo: true}}
		}
		start++
	}
	end := min(start+req.Limit, len(items))
	return catalogPage{Candidates: items[start:end], HasMore: end < len(items), Info: catalogInfo{Version: defaultCatalogVersion, Demo: true}}
}
func stringPtr(s string) *string { return &s }
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
