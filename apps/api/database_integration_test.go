//go:build integration

package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"brutforce-behavior-demo/apps/api/internal/catalogimport"
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"os"
	"reflect"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/pressly/goose/v3"
)

var integrationSetup struct {
	sync.Once
	err   error
	fresh bool
}

// The registered lct-db-test wrapper owns schema reset and holds the zone lock.
// No test drops a persistent schema or relies on rollback across HTTP connections.
func prepareDatabase(t *testing.T) {
	t.Helper()
	if os.Getenv("DATABASE_URL") == "" || os.Getenv("MIGRATION_DATABASE_URL") == "" {
		t.Fatal("integration requires runtime and migration credentials from lct-db-test maks")
	}
	integrationSetup.Do(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
		if err != nil {
			integrationSetup.err = err
			return
		}
		defer db.Close()
		var name string
		if err = db.QueryRowContext(ctx, "SELECT current_database()").Scan(&name); err != nil {
			integrationSetup.err = err
			return
		}
		if name != "lct_test_maks" {
			t.Fatal("refusing integration outside lct_test_maks")
		}
		if err = db.QueryRowContext(ctx, "SELECT to_regclass('public.catalog_items') IS NULL").Scan(&integrationSetup.fresh); err != nil {
			integrationSetup.err = err
			return
		}
		integrationSetup.err = catalogdb.Migrate(ctx, os.Getenv("MIGRATION_DATABASE_URL"), "migrations")
	})
	if integrationSetup.err != nil {
		t.Fatal("test database preparation failed (credential details suppressed)")
	}
}

func realCatalog(t *testing.T) (catalogReader, func()) {
	t.Helper()
	prepareDatabase(t)
	store, closeStore, err := openConfiguredCatalog(context.Background())
	if err != nil {
		t.Fatal("runtime database connection failed")
	}
	pg, ok := store.(postgresCatalogStore)
	if !ok {
		t.Fatal("integration silently used an embedded catalog")
	}
	var name string
	if err := pg.pool.QueryRow(context.Background(), "SELECT current_database()").Scan(&name); err != nil || name != "lct_test_maks" {
		closeStore()
		t.Fatal("runtime must connect only to lct_test_maks")
	}
	return store, closeStore
}

func TestDB000LegacySchemaSnapshotExport(t *testing.T) {
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal("migration database unavailable")
	}
	defer db.Close()
	var existing sql.NullString
	if err := db.QueryRow("SELECT to_regclass('public.catalog_items')::text").Scan(&existing); err != nil {
		t.Fatal(err)
	}
	if existing.Valid {
		t.Skip("requires the registered reset wrapper before other integration tests")
	}
	if err := goose.SetDialect("postgres"); err != nil {
		t.Fatal(err)
	}
	if err := goose.UpToContext(context.Background(), db, "migrations", 1); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO demo_catalog(id,name,winery,year,image,description,display_order) VALUES('legacy-id','Legacy','Cellar',2024,'','Demo',1)`); err != nil {
		t.Fatal(err)
	}
	snapshot, err := catalogimport.Export(context.Background(), db)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.Version != "demo-v1" || snapshot.ManifestSHA256 == "" || len(snapshot.Wines) != 1 || snapshot.Wines[0].Slug != snapshot.Wines[0].ID {
		t.Fatalf("invalid legacy snapshot: %#v", snapshot)
	}
}

func TestDB001FreshMigrationsAndReapply(t *testing.T) {
	prepareDatabase(t)
	if !integrationSetup.fresh {
		t.Fatal("fresh-schema test requires the registered reset wrapper")
	}
	if err := catalogdb.Migrate(context.Background(), os.Getenv("MIGRATION_DATABASE_URL"), "migrations"); err != nil {
		t.Fatal("migration reapply failed")
	}
	store, closeStore := realCatalog(t)
	defer closeStore()
	rows, err := store.List(context.Background())
	if err != nil || !reflect.DeepEqual(rows, postgresDemoWines()) {
		t.Fatal("migrated catalog differs from the synthetic fixture")
	}
}

func TestDB002SeedPreservesEditsAndDoesNotDuplicate(t *testing.T) {
	prepareDatabase(t)
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal("migration connection failed")
	}
	defer db.Close()
	id := demoWines[0].ID
	if _, err = db.Exec("UPDATE catalog_items SET name=$1 WHERE id=$2", "Edited synthetic card", id); err != nil {
		t.Fatal("fixture edit failed")
	}
	defer db.Exec("UPDATE catalog_items SET name=$1 WHERE id=$2", demoWines[0].Name, id)
	for i := 0; i < 2; i++ {
		if err := catalogdb.Seed(context.Background(), db, "migrations"); err != nil {
			t.Fatal("repeated seed failed")
		}
	}
	var count int
	var name string
	if err := db.QueryRow("SELECT count(*) FROM catalog_items").Scan(&count); err != nil || count != len(demoWines) {
		t.Fatal("seed duplicated or removed rows")
	}
	if err := db.QueryRow("SELECT name FROM catalog_items WHERE id=$1", id).Scan(&name); err != nil || name != "Edited synthetic card" {
		t.Fatal("seed overwrote existing data")
	}
}

func TestDB003ActualHTTPQueriesUsePostgresLiterally(t *testing.T) {
	store, closeStore := realCatalog(t)
	defer closeStore()
	handler := newHandlerWithCatalog("", nil, store)
	response := request(t, handler, http.MethodGet, "/v2/catalog", "")
	wantCatalog := postgresDemoWines()
	sort.Slice(wantCatalog, func(i, j int) bool { return wantCatalog[i].ID < wantCatalog[j].ID })
	if response.Code != 200 || !reflect.DeepEqual(decodeResponse(t, response).Candidates, wantCatalog) {
		t.Fatal("HTTP catalog does not match database seed")
	}
	for _, query := range []string{"КАбЕрНе", "Демо", "2022", "%", "_", "' OR 1=1 --", "not-a-wine"} {
		t.Run(query, func(t *testing.T) {
			body, _ := json.Marshal(searchRequest{Scenario: "exact", Query: &query})
			r := request(t, newHandlerWithCatalog("", nil, store), http.MethodPost, "/v1/search", string(body))
			if r.Code != 200 {
				t.Fatalf("query returned HTTP %d", r.Code)
			}
			got := decodeResponse(t, r).Candidates
			want := filterWineList(postgresDemoWines(), &query)
			if !reflect.DeepEqual(got, want) {
				t.Fatal("PostgreSQL search differs from literal substring behavior")
			}
		})
	}
}

func postgresDemoWines() []wine {
	wines := append([]wine(nil), demoWines...)
	for i := range wines {
		wines[i].Slug = wines[i].ID
	}
	return wines
}

func TestDB004DataSurvivesRuntimeReconnect(t *testing.T) {
	prepareDatabase(t)
	db, err := catalogdb.Open(os.Getenv("MIGRATION_DATABASE_URL"))
	if err != nil {
		t.Fatal("migration connection failed")
	}
	defer db.Close()
	id := demoWines[0].ID
	if _, err = db.Exec("UPDATE catalog_items SET description=$1 WHERE id=$2", "Reconnect fixture", id); err != nil {
		t.Fatal("fixture write failed")
	}
	defer db.Exec("UPDATE catalog_items SET description=$1 WHERE id=$2", demoWines[0].Description, id)
	for i := 0; i < 2; i++ {
		store, closeStore := realCatalog(t)
		rows, err := store.List(context.Background())
		closeStore()
		if err != nil || len(rows) == 0 || rows[0].Description != "Reconnect fixture" {
			t.Fatal("data did not survive independent runtime connection")
		}
	}
}

func TestDB005RuntimeCannotChangeSchema(t *testing.T) {
	store, closeStore := realCatalog(t)
	defer closeStore()
	pg := store.(postgresCatalogStore)
	if _, err := pg.List(context.Background()); err != nil {
		t.Fatal("runtime cannot read catalog")
	}
	_, err := pg.pool.Exec(context.Background(), "CREATE TABLE db_test_forbidden (id int)")
	pgerr, ok := err.(*pgconn.PgError)
	if !ok || pgerr.Code != "42501" {
		t.Fatal("runtime DDL must fail with insufficient_privilege")
	}
}
