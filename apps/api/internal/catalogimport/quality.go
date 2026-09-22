package catalogimport

import (
	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"os"
	"sort"
	"strings"
	"time"
)

// QualityReport is machine-readable evidence for the data gate. It never
// asserts DB/HTTP cases: those are post-placement checks owned by deployment.
type QualityReport struct {
	SchemaVersion    uint           `json:"schemaVersion"`
	Kind             string         `json:"kind"`
	Status           string         `json:"status"`
	CatalogVersion   string         `json:"catalogVersion"`
	ManifestSHA256   string         `json:"manifestSHA256"`
	ValidatorVersion string         `json:"validatorVersion"`
	StartedAt        time.Time      `json:"startedAt"`
	CompletedAt      time.Time      `json:"completedAt"`
	DurationMS       int64          `json:"durationMs"`
	Counts           map[string]int `json:"counts"`
	Cases            []QualityCase  `json:"cases"`
}
type QualityCase struct {
	ID       string           `json:"id"`
	Title    string           `json:"title"`
	Section  string           `json:"section"`
	Status   string           `json:"status"`
	Summary  string           `json:"summary"`
	Failures []QualityFailure `json:"failures"`
}
type QualityFailure struct {
	Slug    string `json:"slug,omitempty"`
	Path    string `json:"path,omitempty"`
	Message string `json:"message"`
}

// Validate performs the portable package half (DQ001-008, DQ011).  Errors are
// deliberately capped to keep a corrupt full export from producing huge logs.
func Validate(opts Options, validatorVersion string, previous Snapshot, allowed map[string]bool) QualityReport {
	started := time.Now().UTC()
	wines, aliases, sha, err := load(opts.PackageDir, opts.MediaRoot, opts.Version)
	return validateLoaded(opts, validatorVersion, previous, allowed, started, wines, aliases, sha, err)
}

func validateLoaded(opts Options, validatorVersion string, previous Snapshot, allowed map[string]bool, started time.Time, wines []catalogmodel.Wine, aliases []Alias, sha string, loadErr error) QualityReport {
	r := QualityReport{SchemaVersion: 1, Kind: "catalog-data-quality", Status: "failed", CatalogVersion: opts.Version, ValidatorVersion: validatorVersion, StartedAt: started, Counts: map[string]int{"cards": 0, "aliases": 0, "assets": 0}}
	caseDefs := []struct{ id, title, section string }{
		{"DQ001", "Schema and required fields", "package"}, {"DQ002", "Unique IDs, slugs and aliases", "package"},
		{"DQ003", "Required display image roles", "media"}, {"DQ004", "Local declared files", "media"},
		{"DQ005", "Media integrity and decode", "media"}, {"DQ006", "Declared and decoded image geometry", "media"},
		{"DQ007", "Runtime display-field policy", "package"}, {"DQ008", "Version and manifest integrity", "package"},
		{"DQ011", "Unexpected removed IDs", "comparison"},
	}
	for _, d := range caseDefs {
		r.Cases = append(r.Cases, QualityCase{ID: d.id, Title: d.title, Section: d.section, Status: "not_run", Summary: "not run"})
	}
	r.ManifestSHA256 = sha
	if loadErr != nil {
		idx := qualityFailureCase(loadErr.Error())
		message := loadErr.Error()
		if strings.Contains(message, "manifest") {
			idx = 7
		}
		r.Cases[idx].Status = "failed"
		r.Cases[idx].Summary = "package validation failed"
		r.Cases[idx].Failures = []QualityFailure{{Message: message}}
	} else {
		r.Status = "passed"
		for i := 0; i < 8; i++ {
			r.Cases[i].Status = "passed"
			r.Cases[i].Summary = "passed"
		}
		r.Cases[5].Summary = "decoded dimensions, role bounds, aspect ratios and no-upscale invariants passed"
		r.Cases[6].Summary = "suppressed fields are absent and runtime source URLs are safe"
		r.Counts["cards"], r.Counts["aliases"] = len(wines), len(aliases)
		assets := map[string]bool{}
		for _, w := range wines {
			for _, v := range w.ImageVariants {
				assets[v.Path] = true
			}
		}
		r.Counts["assets"] = len(assets)
		applyRemovalComparison(&r, wines, previous, allowed)
	}
	r.CompletedAt = time.Now().UTC()
	r.DurationMS = r.CompletedAt.Sub(started).Milliseconds()
	return r
}

func applyRemovalComparison(r *QualityReport, wines []catalogmodel.Wine, previous Snapshot, allowed map[string]bool) {
	caseIndex := -1
	for i := range r.Cases {
		if r.Cases[i].ID == "DQ011" {
			caseIndex = i
			break
		}
	}
	if caseIndex < 0 {
		r.Cases = append(r.Cases, QualityCase{ID: "DQ011", Title: "Unexpected removed IDs", Section: "comparison"})
		caseIndex = len(r.Cases) - 1
	}
	c := &r.Cases[caseIndex]
	c.Failures = nil
	if len(previous.Wines) == 0 {
		c.Status, c.Summary, r.Status = "needs_baseline", "previous accepted snapshot is required for removal comparison", "failed"
		return
	}
	now, baseline := map[string]bool{}, map[string]bool{}
	for _, w := range wines {
		now[w.ID] = true
	}
	var missing []string
	for _, w := range previous.Wines {
		baseline[w.ID] = true
		if !now[w.ID] && !allowed[w.ID] {
			missing = append(missing, w.ID)
		}
	}
	for id := range allowed {
		if !baseline[id] {
			missing = append(missing, id+" (not in baseline)")
		} else if now[id] {
			missing = append(missing, id+" (not removed)")
		}
	}
	sort.Strings(missing)
	if len(missing) == 0 {
		c.Status, c.Summary = "passed", "no unexpected removed IDs"
		return
	}
	r.Status, c.Status, c.Summary = "failed", "failed", "candidate removes prior IDs without exact authorization"
	for _, id := range missing {
		if len(c.Failures) == 32 {
			break
		}
		c.Failures = append(c.Failures, QualityFailure{Slug: id, Message: "unexpected removed ID"})
	}
}
func qualityFailureCase(message string) int {
	switch {
	case strings.Contains(message, "alias") || strings.Contains(message, "duplicate"):
		return 1
	case strings.Contains(message, "requires all display image roles") || strings.Contains(message, "null image") || strings.Contains(message, "variant role"):
		return 2
	case strings.Contains(message, "unmanifested") || strings.Contains(message, "path") || strings.Contains(message, "symlink") || strings.Contains(message, "not exist"):
		return 3
	case strings.Contains(message, "checksum") || strings.Contains(message, "MIME") || strings.Contains(message, "decode") || strings.Contains(message, "WebP"):
		return 4
	case strings.Contains(message, "dimension") || strings.Contains(message, "long-side") || strings.Contains(message, "bound"):
		return 5
	case strings.Contains(message, "policy") || strings.Contains(message, "source_url"):
		return 6
	default:
		return 0
	}
}

func ReadSnapshot(path string) (Snapshot, error) {
	var s Snapshot
	raw, err := os.ReadFile(path)
	if err != nil {
		return s, err
	}
	if err = json.Unmarshal(raw, &s); err != nil {
		return s, err
	}
	if len(s.Wines) == 0 {
		return s, errors.New("snapshot has no wines")
	}
	return s, nil
}
func ReadAllowedRemovals(path string) (map[string]bool, error) {
	var d struct {
		IDs         []string `json:"ids"`
		Reason      string   `json:"reason"`
		ApprovalRef string   `json:"approvalRef"`
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if err = json.Unmarshal(raw, &d); err != nil {
		return nil, err
	}
	if d.Reason == "" || d.ApprovalRef == "" || len(d.IDs) == 0 {
		return nil, errors.New("allow-removed requires ids, reason and approvalRef")
	}
	out := map[string]bool{}
	for _, id := range d.IDs {
		if id == "" || out[id] {
			return nil, errors.New("invalid allow-removed ids")
		}
		out[id] = true
	}
	return out, nil
}

// VerifyDB adds DQ009 after an import. It compares the complete accepted
// projection, aliases, active version, and registered source-manifest digest.
func VerifyDB(ctx context.Context, db *sql.DB, opts Options, validatorVersion string, previous Snapshot, allowed map[string]bool) QualityReport {
	started := time.Now().UTC()
	wines, aliases, sha, err := load(opts.PackageDir, opts.MediaRoot, opts.Version)
	r := validateLoaded(opts, validatorVersion, previous, allowed, started, wines, aliases, sha, err)
	dq := QualityCase{ID: "DQ009", Title: "Target database projection", Section: "placement", Status: "failed", Summary: "accepted package could not be loaded"}
	if err != nil {
		dq.Failures = []QualityFailure{{Message: err.Error()}}
	} else {
		dq = verifyProjection(ctx, db, opts.Version, wines, aliases, sha)
	}
	r.Cases = append(r.Cases, dq)
	if dq.Status != "passed" {
		r.Status = "failed"
	}
	r.CompletedAt = time.Now().UTC()
	r.DurationMS = r.CompletedAt.Sub(r.StartedAt).Milliseconds()
	return r
}
