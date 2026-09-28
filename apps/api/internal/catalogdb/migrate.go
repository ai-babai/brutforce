package catalogdb

import (
	"context"
	"database/sql"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"
	"os"
	"path/filepath"
)

func Open(url string) (*sql.DB, error) {
	config, err := pgx.ParseConfig(url)
	if err != nil {
		return nil, err
	}
	return stdlib.OpenDB(*config), nil
}
func Seed(ctx context.Context, db *sql.DB, dir string) error {
	// An imported catalog owns the active state.  Never let the synthetic seed
	// repopulate or overwrite it when migrations are re-applied.
	var active bool
	err := db.QueryRowContext(ctx, "SELECT EXISTS (SELECT 1 FROM catalog_state WHERE singleton)").Scan(&active)
	if err == nil && active {
		return nil
	}
	if err != nil {
		// Before 00002 there is no catalog_state table.  Goose normally applies
		// all migrations first, but retain compatibility for callers of Seed.
		return err
	}
	seed, err := os.ReadFile(filepath.Join(dir, "seeds", "demo_catalog.sql"))
	if err != nil {
		return err
	}
	_, err = db.ExecContext(ctx, string(seed))
	return err
}
func Migrate(ctx context.Context, url, dir string) error {
	return migrate(ctx, url, dir, true)
}
func MigrateSchema(ctx context.Context, url, dir string) error {
	return migrate(ctx, url, dir, false)
}
func migrate(ctx context.Context, url, dir string, seed bool) error {
	db, err := Open(url)
	if err != nil {
		return err
	}
	defer db.Close()
	if err = goose.SetDialect("postgres"); err != nil {
		return err
	}
	if err = goose.UpContext(ctx, db, dir); err != nil {
		return err
	}
	if seed {
		return Seed(ctx, db, dir)
	}
	return nil
}
