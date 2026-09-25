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
	mediaRoot := flag.String("media-root", "", "global catalog media directory for catalog-release-1")
	version := flag.String("version", "", "immutable catalog version")
	dryRun := flag.Bool("dry-run", false, "validate only; make no database changes")
	reportOut := flag.String("report-out", "", "write catalog data-quality JSON report")
	validatorVersion := flag.String("validator-version", "", "validator build/policy digest")
	previousSnapshot := flag.String("previous-snapshot", "", "accepted snapshot for exact removed-ID comparison")
	allowRemoved := flag.String("allow-removed", "", "JSON with exact ids, reason and approvalRef")
	verifyDB := flag.Bool("verify-db", false, "verify target DB against the accepted package (DQ009)")
	compareIDs := flag.Bool("compare-ids", false, "compare accepted package IDs with the previous snapshot and exit")
	acceptedReport := flag.String("accepted-report", "", "prior passing report bound to the current manifest and validator")
	exportSnapshot := flag.String("export-snapshot", "", "export current DB snapshot and exit")
	snapshotOut := flag.String("snapshot-out", "", "path for rollback snapshot before import")
	restore := flag.String("restore", "", "restore a prior snapshot instead of importing")
	flag.Parse()
	if *exportSnapshot == "" && *restore == "" && (*packageDir == "" || *version == "") {
		fail("-package and -version are required")
	}
	if *exportSnapshot == "" && !*dryRun && !*verifyDB && !*compareIDs && *restore == "" && *snapshotOut == "" {
		fail("-snapshot-out is required for a non-dry-run import")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	if *exportSnapshot != "" {
		url := os.Getenv("MIGRATION_DATABASE_URL")
		if url == "" {
			fail("MIGRATION_DATABASE_URL is required")
		}
		db, err := catalogdb.Open(url)
		if err != nil {
			fail("database connection configuration is invalid")
		}
		defer db.Close()
		snapshot, err := catalogimport.Export(ctx, db)
		if err != nil {
			fail("cannot export current snapshot")
		}
		if err := writeSnapshot(*exportSnapshot, snapshot); err != nil {
			fail("cannot write snapshot")
		}
		return
	}
	if *compareIDs {
		if *acceptedReport == "" || *previousSnapshot == "" || *validatorVersion == "" {
			fail("-compare-ids requires -accepted-report, -previous-snapshot and -validator-version")
		}
		previous, err := catalogimport.ReadSnapshot(*previousSnapshot)
		if err != nil {
			fail("previous snapshot is invalid")
		}
		var allowed map[string]bool
		if *allowRemoved != "" {
			allowed, err = catalogimport.ReadAllowedRemovals(*allowRemoved)
			if err != nil {
				fail("allow-removed is invalid")
			}
		}
		report, err := catalogimport.CompareAccepted(catalogimport.Options{PackageDir: *packageDir, MediaRoot: *mediaRoot, Version: *version}, *acceptedReport, *validatorVersion, previous, allowed)
		if err != nil {
			fail("accepted report comparison failed: " + err.Error())
		}
		if *reportOut != "" && writeReport(*reportOut, report) != nil {
			fail("cannot write quality report")
		}
		if report.Status != "passed" {
			fail("catalog ID comparison failed")
		}
		fmt.Printf("catalog %s: accepted IDs match removal policy\n", *version)
		return
	}
	if *dryRun {
		var previous catalogimport.Snapshot
		var allowed map[string]bool
		var err error
		if *previousSnapshot != "" {
			previous, err = catalogimport.ReadSnapshot(*previousSnapshot)
			if err != nil {
				fail("previous snapshot is invalid")
			}
		}
		if *allowRemoved != "" {
			allowed, err = catalogimport.ReadAllowedRemovals(*allowRemoved)
			if err != nil {
				fail("allow-removed is invalid")
			}
		}
		report := catalogimport.Validate(catalogimport.Options{PackageDir: *packageDir, MediaRoot: *mediaRoot, Version: *version, DryRun: true}, *validatorVersion, previous, allowed)
		if *reportOut != "" {
			if err := writeReport(*reportOut, report); err != nil {
				fail("cannot write quality report")
			}
		}
		if report.Status != "passed" {
			fail("catalog dry run failed")
		}
		fmt.Printf("catalog %s: %d wines, %d aliases (dry run)\n", *version, report.Counts["cards"], report.Counts["aliases"])
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
	if *verifyDB {
		var previous catalogimport.Snapshot
		var allowed map[string]bool
		if *previousSnapshot != "" {
			previous, err = catalogimport.ReadSnapshot(*previousSnapshot)
			if err != nil {
				fail("previous snapshot is invalid")
			}
		}
		if *allowRemoved != "" {
			allowed, err = catalogimport.ReadAllowedRemovals(*allowRemoved)
			if err != nil {
				fail("allow-removed is invalid")
			}
		}
		var report catalogimport.QualityReport
		if *acceptedReport != "" {
			report = catalogimport.VerifyDBAccepted(ctx, db, catalogimport.Options{PackageDir: *packageDir, MediaRoot: *mediaRoot, Version: *version}, *acceptedReport, *validatorVersion, previous, allowed)
		} else {
			report = catalogimport.VerifyDB(ctx, db, catalogimport.Options{PackageDir: *packageDir, MediaRoot: *mediaRoot, Version: *version}, *validatorVersion, previous, allowed)
		}
		if *reportOut != "" {
			if err := writeReport(*reportOut, report); err != nil {
				fail("cannot write quality report")
			}
		}
		if report.Status != "passed" {
			fail("catalog DB verification failed")
		}
		return
	}
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
	opts := catalogimport.Options{PackageDir: *packageDir, MediaRoot: *mediaRoot, Version: *version, DryRun: *dryRun}
	var result catalogimport.Result
	if *acceptedReport != "" {
		if *validatorVersion == "" {
			fail("-accepted-report requires -validator-version")
		}
		result, err = catalogimport.ImportAccepted(ctx, db, opts, *acceptedReport, *validatorVersion)
	} else {
		result, err = catalogimport.Import(ctx, db, opts)
	}
	if err != nil {
		fail("catalog import failed: " + err.Error())
	}
	fmt.Printf("catalog %s: %d wines, %d aliases%s\n", result.Version, result.Wines, result.Aliases, map[bool]string{true: " (dry run)", false: ""}[*dryRun])
}
func writeReport(path string, report catalogimport.QualityReport) error {
	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(raw, '\n'), 0600)
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
