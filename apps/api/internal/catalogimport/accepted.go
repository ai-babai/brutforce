package catalogimport

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"time"

	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
)

var acceptedRequiredCases = []string{"DQ001", "DQ002", "DQ003", "DQ004", "DQ005", "DQ006", "DQ007", "DQ008", "DQ011"}

// LoadAcceptedProjection trusts media bytes only after binding a prior passing
// report to this exact manifest and validator. It still rechecks all structural
// metadata used to construct the database projection.
func LoadAcceptedProjection(opts Options, reportPath, expectedValidator string) ([]catalogmodel.Wine, []Alias, string, QualityReport, error) {
	var report QualityReport
	if reportPath == "" || expectedValidator == "" {
		return nil, nil, "", report, errors.New("accepted report and expected validator are required")
	}
	rawReport, err := os.ReadFile(reportPath)
	if err != nil {
		return nil, nil, "", report, err
	}
	if err := json.Unmarshal(rawReport, &report); err != nil {
		return nil, nil, "", report, err
	}
	root, err := filepath.Abs(opts.PackageDir)
	if err != nil {
		return nil, nil, "", report, err
	}
	rawManifest, err := readSafe(root, "manifest.json")
	if err != nil {
		return nil, nil, "", report, err
	}
	sum := sha256.Sum256(rawManifest)
	manifestSHA := hex.EncodeToString(sum[:])
	if err := validateAcceptedReport(report, opts.Version, manifestSHA, expectedValidator); err != nil {
		return nil, nil, "", report, err
	}
	wines, aliases, err := loadAcceptedReleaseProjection(root, opts.Version, rawManifest)
	return wines, aliases, manifestSHA, report, err
}

// ImportAccepted imports the structurally reconstructed projection backed by
// prior accepted validation evidence. replace retains the same transaction,
// immutable-version, idempotence and active-drift checks as a full import.
func ImportAccepted(ctx context.Context, db *sql.DB, opts Options, reportPath, expectedValidator string) (Result, error) {
	wines, aliases, manifestSHA, _, err := LoadAcceptedProjection(opts, reportPath, expectedValidator)
	if err != nil {
		return Result{}, err
	}
	result := Result{Version: opts.Version, Wines: len(wines), Aliases: len(aliases), DryRun: opts.DryRun, ManifestSHA256: manifestSHA}
	if opts.DryRun {
		return result, nil
	}
	if err := replace(ctx, db, opts.Version, wines, aliases, manifestSHA); err != nil {
		return Result{}, err
	}
	return result, nil
}

func validateAcceptedReport(report QualityReport, version, manifestSHA, validator string) error {
	if report.SchemaVersion != 1 || report.Kind != "catalog-data-quality" || report.Status != "passed" || report.CatalogVersion != version || report.ManifestSHA256 != manifestSHA || report.ValidatorVersion != validator {
		return errors.New("accepted report does not match catalog, manifest, or validator")
	}
	passed := map[string]bool{}
	for _, c := range report.Cases {
		if passed[c.ID] || c.Status != "passed" || len(c.Failures) != 0 {
			return fmt.Errorf("accepted report case %s is not uniquely passing", c.ID)
		}
		passed[c.ID] = true
	}
	for _, id := range acceptedRequiredCases {
		if !passed[id] {
			return fmt.Errorf("accepted report is missing passing case %s", id)
		}
	}
	return nil
}

func loadAcceptedReleaseProjection(root, version string, rawManifest []byte) ([]catalogmodel.Wine, []Alias, error) {
	var manifest releaseManifest
	if json.Unmarshal(rawManifest, &manifest) != nil || manifest.SchemaVersion != "catalog-release-1" || manifest.CatalogVersion != version {
		return nil, nil, errors.New("accepted release manifest is invalid")
	}
	required := map[string]bool{"wines.jsonl": false, "aliases.json": false, "catalog.json": false, "internal/display-policy.json": false, "PREPARATION.md": false}
	for _, f := range manifest.Files {
		if _, ok := required[f.Path]; !ok || required[f.Path] || f.Bytes < 0 || !isSHA256(f.SHA256) {
			return nil, nil, fmt.Errorf("invalid accepted manifest file %q", f.Path)
		}
		required[f.Path] = true
	}
	for path, found := range required {
		if !found {
			return nil, nil, fmt.Errorf("accepted manifest missing %s", path)
		}
	}
	media := map[string]packageImage{}
	for _, m := range manifest.Media {
		if _, exists := media[m.Path]; exists || !validMediaKey(m.Path, m.SHA256) || m.Bytes < 1 || m.Width < 1 || m.Height < 1 || m.Width > maxImageDimension || m.Height > maxImageDimension || m.Width*m.Height > maxImagePixels || m.MIMEType != "image/webp" {
			return nil, nil, fmt.Errorf("invalid accepted manifest media %q", m.Path)
		}
		media[m.Path] = packageImage{Path: m.Path, SHA256: strings.ToLower(m.SHA256), MIMEType: m.MIMEType, Width: m.Width, Height: m.Height, Bytes: m.Bytes}
	}
	catalog, err := readSafe(root, "catalog.json")
	if err != nil {
		return nil, nil, err
	}
	var schema struct {
		SchemaVersion string `json:"schema_version"`
	}
	if json.Unmarshal(catalog, &schema) != nil || schema.SchemaVersion != "svoe-display-catalog-2.0.0" {
		return nil, nil, errors.New("accepted catalog schema is invalid")
	}
	rawWines, err := readSafe(root, "wines.jsonl")
	if err != nil {
		return nil, nil, err
	}
	if err := validateDisplayPolicy(root, rawWines); err != nil {
		return nil, nil, err
	}
	records, err := parseWines(rawWines)
	if err != nil || len(records) == 0 {
		return nil, nil, errors.New("accepted release has no valid wines")
	}
	wines := make([]catalogmodel.Wine, 0, len(records))
	ids, slugs := map[string]bool{}, map[string]bool{}
	for _, record := range records {
		wine, err := acceptedWine(record)
		if err != nil {
			return nil, nil, err
		}
		if wine.ID == "" || ids[wine.ID] || slugs[wine.Slug] {
			return nil, nil, errors.New("duplicate accepted catalog ID or slug")
		}
		ids[wine.ID], slugs[wine.Slug] = true, true
		master, exists := media[wine.Image]
		masterMatches := false
		for _, variant := range wine.ImageVariants {
			if variant.Role == "original" && sameImageMetadata(master, variant) {
				masterMatches = true
			}
		}
		if !exists || !masterMatches {
			return nil, nil, fmt.Errorf("%s references unmanifested master image", wine.Slug)
		}
		for _, variant := range wine.ImageVariants {
			declared, exists := media[variant.Path]
			if !exists || !sameImageMetadata(declared, variant) {
				return nil, nil, fmt.Errorf("%s references unmanifested variant", wine.Slug)
			}
		}
		wines = append(wines, wine)
	}
	aliases, err := loadAliases(root, slugs)
	if err != nil {
		return nil, nil, err
	}
	sort.Slice(wines, func(i, j int) bool { return wines[i].ID < wines[j].ID })
	return wines, aliases, nil
}

func sameImageMetadata(declared packageImage, projected catalogmodel.ImageVariant) bool {
	return declared.Path == projected.Path && strings.EqualFold(declared.SHA256, projected.SHA256) && declared.MIMEType == projected.MIMEType && declared.Width == projected.Width && declared.Height == projected.Height && declared.Bytes == projected.Bytes
}

func acceptedWine(r packageWine) (catalogmodel.Wine, error) {
	if r.ID == "" || r.Slug == "" || strings.ContainsAny(r.ID+r.Slug, "/\\") || r.Title == "" || r.Producer == "" {
		return catalogmodel.Wine{}, errors.New("accepted wine requires safe ID, slug, title and producer")
	}
	if r.Year != nil && (*r.Year < 1000 || *r.Year > time.Now().Year()+1) {
		return catalogmodel.Wine{}, fmt.Errorf("invalid year for %q", r.Slug)
	}
	parsedURL, err := url.Parse(r.SourceURL)
	if r.SourceURL != "" && (err != nil || (parsedURL.Scheme != "https" && parsedURL.Scheme != "http") || parsedURL.Host == "") {
		return catalogmodel.Wine{}, fmt.Errorf("invalid source_url for %q", r.Slug)
	}
	if !r.imagePresent || r.imageNull {
		return catalogmodel.Wine{}, fmt.Errorf("%s requires a display image", r.Slug)
	}
	sanitizeAlcohol(&r)
	master, err := acceptedImage(r.Image, "")
	if err != nil {
		return catalogmodel.Wine{}, err
	}
	w := catalogmodel.Wine{ID: r.ID, Slug: r.Slug, Name: r.Title, Winery: r.Producer, Description: r.Description, Image: master.Path, SourceURL: r.SourceURL, SourceSnapshotDate: r.SourceSnapshotDate, Region: r.Region, Grapes: r.Grapes, CategoryAndSweetness: r.CategoryAndSweetness, Color: r.Color, Sugar: r.Sugar, AlcoholPercent: r.AlcoholPercent, AlcoholMinPercent: r.AlcoholMinPercent, AlcoholMaxPercent: r.AlcoholMaxPercent, VolumeL: r.VolumeL, Ratings: r.Ratings}
	if r.Year != nil {
		w.Year = *r.Year
	}
	roles := map[string]bool{}
	for _, variant := range r.Image.Variants {
		if roles[variant.Role] || (variant.Role != "thumbnail" && variant.Role != "card" && variant.Role != "original") {
			return catalogmodel.Wine{}, errors.New("invalid accepted image variant role")
		}
		roles[variant.Role] = true
		iv, err := acceptedImage(variant.packageImage, variant.Role)
		if err != nil {
			return catalogmodel.Wine{}, err
		}
		dir := map[string]string{"thumbnail": "400/", "card": "800/", "original": "original/"}[variant.Role]
		if !strings.HasPrefix(iv.Path, dir) {
			return catalogmodel.Wine{}, errors.New("accepted variant path does not match its role")
		}
		if err := validateVariantGeometry(master, iv); err != nil {
			return catalogmodel.Wine{}, err
		}
		bound := map[string]int{"thumbnail": 400, "card": 800, "original": 1600}[variant.Role]
		if maxSide(iv.Width, iv.Height) > bound {
			return catalogmodel.Wine{}, errors.New("accepted variant exceeds role bound")
		}
		w.ImageVariants = append(w.ImageVariants, iv)
	}
	if !(roles["thumbnail"] && roles["card"] && roles["original"]) || maxSide(master.Width, master.Height) > 1600 {
		return catalogmodel.Wine{}, errors.New("accepted wine requires bounded thumbnail, card and original variants")
	}
	sort.Slice(w.ImageVariants, func(i, j int) bool { return w.ImageVariants[i].Role < w.ImageVariants[j].Role })
	normalizeWine(&w)
	return w, nil
}

func acceptedImage(spec packageImage, role string) (catalogmodel.ImageVariant, error) {
	if !validMediaKey(spec.Path, spec.SHA256) || spec.MIMEType != "image/webp" || spec.Width < 1 || spec.Height < 1 || spec.Bytes < 1 || spec.Width > maxImageDimension || spec.Height > maxImageDimension || spec.Width*spec.Height > maxImagePixels {
		return catalogmodel.ImageVariant{}, errors.New("accepted image metadata is invalid")
	}
	return catalogmodel.ImageVariant{Role: role, Path: spec.Path, Width: spec.Width, Height: spec.Height, Bytes: spec.Bytes, MIMEType: spec.MIMEType, SHA256: strings.ToLower(spec.SHA256)}, nil
}

func isSHA256(value string) bool {
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size
}

func CompareAccepted(opts Options, reportPath, validator string, previous Snapshot, allowed map[string]bool) (QualityReport, error) {
	wines, aliases, _, report, err := LoadAcceptedProjection(opts, reportPath, validator)
	if err != nil {
		return QualityReport{}, err
	}
	report.Counts["cards"], report.Counts["aliases"] = len(wines), len(aliases)
	applyRemovalComparison(&report, wines, previous, allowed)
	return report, nil
}

func VerifyDBAccepted(ctx context.Context, db *sql.DB, opts Options, reportPath, validator string, previous Snapshot, allowed map[string]bool) QualityReport {
	wines, aliases, sha, report, err := LoadAcceptedProjection(opts, reportPath, validator)
	if err != nil {
		return failedAcceptedReport(opts, validator, err)
	}
	applyRemovalComparison(&report, wines, previous, allowed)
	dq := verifyProjection(ctx, db, opts.Version, wines, aliases, sha)
	report.Cases = append(report.Cases, dq)
	if dq.Status != "passed" {
		report.Status = "failed"
	}
	report.CompletedAt = time.Now().UTC()
	report.DurationMS = report.CompletedAt.Sub(report.StartedAt).Milliseconds()
	return report
}

func failedAcceptedReport(opts Options, validator string, err error) QualityReport {
	now := time.Now().UTC()
	return QualityReport{SchemaVersion: 1, Kind: "catalog-data-quality", Status: "failed", CatalogVersion: opts.Version, ValidatorVersion: validator, StartedAt: now, CompletedAt: now, Counts: map[string]int{}, Cases: []QualityCase{{ID: "DQ008", Title: "Accepted validation evidence", Section: "package", Status: "failed", Summary: "accepted report rejected", Failures: []QualityFailure{{Message: err.Error()}}}}}
}

func verifyProjection(ctx context.Context, db *sql.DB, version string, wines []catalogmodel.Wine, aliases []Alias, sha string) QualityCase {
	dq := QualityCase{ID: "DQ009", Title: "Target database projection", Section: "placement", Status: "passed", Summary: "target database matches accepted package"}
	actual, exportErr := Export(ctx, db)
	var registered string
	versionErr := db.QueryRowContext(ctx, "SELECT package_sha256 FROM catalog_versions WHERE version=$1", version).Scan(&registered)
	if exportErr != nil || versionErr != nil || actual.Version != version || registered != sha || !reflect.DeepEqual(actual.Wines, wines) || !reflect.DeepEqual(actual.Aliases, aliases) {
		dq.Status, dq.Summary = "failed", "target database differs from accepted package"
		if exportErr != nil {
			dq.Failures = append(dq.Failures, QualityFailure{Message: exportErr.Error()})
		}
		if versionErr != nil {
			dq.Failures = append(dq.Failures, QualityFailure{Message: versionErr.Error()})
		}
		if actual.Version != version {
			dq.Failures = append(dq.Failures, QualityFailure{Message: "active catalog version differs"})
		}
		if registered != sha {
			dq.Failures = append(dq.Failures, QualityFailure{Message: "registered manifest SHA differs"})
		}
		if !reflect.DeepEqual(actual.Wines, wines) {
			dq.Failures = append(dq.Failures, QualityFailure{Message: firstProjectionDifference(actual.Wines, wines)})
		}
		if !reflect.DeepEqual(actual.Aliases, aliases) {
			dq.Failures = append(dq.Failures, QualityFailure{Message: "alias projection differs"})
		}
	}
	return dq
}

func firstProjectionDifference(actual, expected []catalogmodel.Wine) string {
	if len(actual) != len(expected) {
		return fmt.Sprintf("catalog item projection differs: row count %d, expected %d", len(actual), len(expected))
	}
	for i := range expected {
		if reflect.DeepEqual(actual[i], expected[i]) {
			continue
		}
		if actual[i].ID != expected[i].ID {
			return fmt.Sprintf("catalog item projection differs at row %d: id %q, expected %q", i, actual[i].ID, expected[i].ID)
		}
		actualValue, expectedValue := reflect.ValueOf(actual[i]), reflect.ValueOf(expected[i])
		typeOfWine := actualValue.Type()
		for field := 0; field < actualValue.NumField(); field++ {
			if !reflect.DeepEqual(actualValue.Field(field).Interface(), expectedValue.Field(field).Interface()) {
				return fmt.Sprintf("catalog item projection differs for id %q slug %q: field %s", expected[i].ID, expected[i].Slug, typeOfWine.Field(field).Name)
			}
		}
	}
	return "catalog item projection differs"
}
