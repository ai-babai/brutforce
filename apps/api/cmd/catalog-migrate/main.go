package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"context"
	"flag"
	"log"
	"os"
	"time"
)

func main() {
	schemaOnly := flag.Bool("schema-only", false, "migrate schema without synthetic demo cards (for the full catalog)")
	flag.Parse()
	url := os.Getenv("MIGRATION_DATABASE_URL")
	if url == "" {
		log.Fatal("MIGRATION_DATABASE_URL is required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	var err error
	if *schemaOnly {
		err = catalogdb.MigrateSchema(ctx, url, "migrations")
	} else {
		err = catalogdb.Migrate(ctx, url, "migrations")
	}
	if err != nil {
		log.Fatal("catalog migration failed; check database availability, permissions and migration files")
	}
}
