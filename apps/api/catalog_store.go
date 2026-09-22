package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"sort"
	"strconv"
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
	return pageWineSlice(filterWineList(sortedWines(demoWines), stringPtr(req.Query)), req), nil
}
func (embeddedCatalogStore) Resolve(_ context.Context, slug string) (wine, string, error) {
	for _, item := range demoWines {
		if item.ID == slug {
			return item, item.ID, nil
		}
	}
	return wine{}, "", errCatalogNotFound
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
	rows, err := tx.Query(queryCtx, `SELECT id, slug, name, winery, year, image, description, metadata FROM catalog_items WHERE ($1 = '' OR strpos(lower(name), lower($1)) > 0 OR strpos(lower(winery), lower($1)) > 0 OR strpos(COALESCE(year::text, ''), $1) > 0) AND ($2 = '' OR id > $2) ORDER BY id LIMIT $3`, req.Query, req.AfterID, req.Limit+1)
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
func filterWineList(catalog []wine, query *string) []wine {
	if query == nil {
		return append([]wine(nil), catalog...)
	}
	needle := strings.ToLower(strings.TrimSpace(*query))
	out := make([]wine, 0, len(catalog))
	for _, item := range catalog {
		if strings.Contains(strings.ToLower(item.Name), needle) || strings.Contains(strings.ToLower(item.Winery), needle) || (item.Year != 0 && strings.Contains(strconv.Itoa(item.Year), needle)) {
			out = append(out, item)
		}
	}
	return out
}
func sortedWines(in []wine) []wine {
	out := append([]wine(nil), in...)
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}
func pageWineSlice(items []wine, req catalogPageRequest) catalogPage {
	start := 0
	for start < len(items) && items[start].ID <= req.AfterID {
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
