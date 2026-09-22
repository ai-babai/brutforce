// catalog-import imports a validated public catalog package using the migration
// database role. It writes a rollback snapshot before changing the active set.
package main

import (
	"brutforce-behavior-demo/apps/api/internal/catalogdb"
	"brutforce-behavior-demo/apps/api/internal/catalogimport"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

func main() {
	packageDir := flag.String("package", "", "catalog package directory containing public/")
	version := flag.String("version", "", "immutable catalog version")
	dryRun := flag.Bool("dry-run", false, "validate only; make no database changes")
	snapshotOut := flag.String("snapshot-out", "", "path for rollback snapshot before import")
	restore := flag.String("restore", "", "restore a prior snapshot instead of importing")
	flag.Parse()
	if *restore == "" && (*packageDir == "" || *version == "") {
		fail("-package and -version are required")
	}
	if !*dryRun && *restore == "" && *snapshotOut == "" {
		fail("-snapshot-out is required for a non-dry-run import")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	if *dryRun {
		result, err := catalogimport.Import(ctx, nil, catalogimport.Options{PackageDir: *packageDir, Version: *version, DryRun: true})
		if err != nil {
			fail("catalog dry run failed: " + err.Error())
		}
		fmt.Printf("catalog %s: %d wines, %d aliases (dry run)\n", result.Version, result.Wines, result.Aliases)
		return
	}
	url := os.Getenv("MIGRATION_DATABASE_URL")
	if url == "" {
		fail("MIGRATION_DATABASE_URL is required")
	}
	db, err := catalogdb.Open(url)
	if err != nil {
		fail("database connection configuration is invalid")
	}
	defer db.Close()
	if *restore != "" {
		raw, err := os.ReadFile(*restore)
		if err != nil {
			fail("cannot read rollback snapshot")
		}
		var snapshot catalogimport.Snapshot
		if json.Unmarshal(raw, &snapshot) != nil {
			fail("rollback snapshot is invalid")
		}
		if err := catalogimport.Restore(ctx, db, snapshot); err != nil {
			fail("rollback failed")
		}
		fmt.Printf("restored catalog version %s (%d wines)\n", snapshot.Version, len(snapshot.Wines))
		return
	}
	if !*dryRun {
		snapshot, err := catalogimport.Export(ctx, db)
		if err != nil {
			fail("cannot export current rollback snapshot")
		}
		if err := writeSnapshot(*snapshotOut, snapshot); err != nil {
			fail("cannot write rollback snapshot")
		}
	}
	result, err := catalogimport.Import(ctx, db, catalogimport.Options{PackageDir: *packageDir, Version: *version, DryRun: *dryRun})
	if err != nil {
		fail("catalog import failed: " + err.Error())
	}
	fmt.Printf("catalog %s: %d wines, %d aliases%s\n", result.Version, result.Wines, result.Aliases, map[bool]string{true: " (dry run)", false: ""}[*dryRun])
}
func writeSnapshot(path string, snapshot catalogimport.Snapshot) error {
	raw, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".catalog-snapshot-")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if _, err = tmp.Write(append(raw, '\n')); err != nil {
		tmp.Close()
		return err
	}
	if err = tmp.Chmod(0600); err == nil {
		err = tmp.Close()
	}
	if err != nil {
		return err
	}
	return os.Rename(name, path)
}
func fail(message string) { fmt.Fprintln(os.Stderr, message); os.Exit(2) }
