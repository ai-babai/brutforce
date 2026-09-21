package main

import (
	"context"
	"errors"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

const catalogQueryTimeout = 2 * time.Second

var errCatalogUnavailable = errors.New("catalog unavailable")

type catalogReader interface {
	List(context.Context) ([]wine, error)
	Search(context.Context, *string) ([]wine, error)
}

type embeddedCatalogStore struct{}

func (embeddedCatalogStore) List(context.Context) ([]wine, error) {
	return append([]wine(nil), demoWines...), nil
}

func (embeddedCatalogStore) Search(_ context.Context, query *string) ([]wine, error) {
	return filterWineList(demoWines, query), nil
}

type postgresCatalogStore struct {
	pool *pgxpool.Pool
}

func openConfiguredCatalog(ctx context.Context) (catalogReader, func(), error) {
	url := os.Getenv("DATABASE_URL")
	if url == "" {
		return embeddedCatalogStore{}, func() {}, nil
	}
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, nil, errCatalogUnavailable
	}
	config.MaxConns = 4
	config.MinConns = 0
	config.MaxConnLifetime = 5 * time.Minute
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
	return postgresCatalogStore{pool: pool}, pool.Close, nil
}

func (store postgresCatalogStore) List(ctx context.Context) ([]wine, error) {
	return store.query(ctx, "SELECT id, name, winery, year, image, description FROM demo_catalog ORDER BY display_order", nil)
}

func (store postgresCatalogStore) Search(ctx context.Context, query *string) ([]wine, error) {
	if query == nil {
		return store.List(ctx)
	}
	needle := strings.ToLower(strings.TrimSpace(*query))
	return store.query(ctx, `SELECT id, name, winery, year, image, description FROM demo_catalog
WHERE strpos(lower(name), $1) > 0 OR strpos(lower(winery), $1) > 0 OR strpos(CAST(year AS text), $1) > 0
ORDER BY display_order`, []any{needle})
}

func (store postgresCatalogStore) query(ctx context.Context, sql string, args []any) ([]wine, error) {
	queryCtx, cancel := context.WithTimeout(ctx, catalogQueryTimeout)
	defer cancel()
	rows, err := store.pool.Query(queryCtx, sql, args...)
	if err != nil {
		return nil, errCatalogUnavailable
	}
	defer rows.Close()
	result := make([]wine, 0, 8)
	for rows.Next() {
		var candidate wine
		if err := rows.Scan(&candidate.ID, &candidate.Name, &candidate.Winery, &candidate.Year, &candidate.Image, &candidate.Description); err != nil {
			return nil, errCatalogUnavailable
		}
		result = append(result, candidate)
	}
	if rows.Err() != nil {
		return nil, errCatalogUnavailable
	}
	return result, nil
}

func filterWineList(catalog []wine, query *string) []wine {
	if query == nil {
		return append([]wine(nil), catalog...)
	}
	needle := strings.ToLower(strings.TrimSpace(*query))
	filtered := make([]wine, 0, len(catalog))
	for _, candidate := range catalog {
		if strings.Contains(strings.ToLower(candidate.Name), needle) || strings.Contains(strings.ToLower(candidate.Winery), needle) || strings.Contains(strconv.Itoa(candidate.Year), needle) {
			filtered = append(filtered, candidate)
		}
	}
	return filtered
}
