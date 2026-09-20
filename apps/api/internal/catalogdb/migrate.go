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
	seed, err := os.ReadFile(filepath.Join(dir, "seeds", "demo_catalog.sql"))
	if err != nil {
		return err
	}
	_, err = db.ExecContext(ctx, string(seed))
	return err
}
func Migrate(ctx context.Context, url, dir string) error {
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
	return Seed(ctx, db, dir)
}
