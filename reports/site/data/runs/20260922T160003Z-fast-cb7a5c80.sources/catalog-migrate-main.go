package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"context"
	"log"
	"os"
	"time"
)

func main() {
	url := os.Getenv("MIGRATION_DATABASE_URL")
	if url == "" {
		log.Fatal("MIGRATION_DATABASE_URL is required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := catalogdb.Migrate(ctx, url, "migrations"); err != nil {
		log.Fatal("catalog migration failed; check database availability, permissions and migration files")
	}
}
