// Package catalogimport validates a versioned public catalog package and swaps
// it into PostgreSQL as one transaction. It never reads client supplied paths.
package catalogimport

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	_ "golang.org/x/image/webp"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
)

const (
	maxImageBytes     int64 = 20 << 20
	maxImagePixels          = 25_000_000
	maxImageDimension       = 12_000
)

type Options struct {
	PackageDir string
	Version    string
	DryRun     bool
}

type Result struct {
	Version        string
	Wines, Aliases int
	DryRun         bool
}

type Snapshot struct {
	Version string              `json:"version"`
	Wines   []catalogmodel.Wine `json:"wines"`
	Aliases []Alias             `json:"aliases"`
}
type Alias struct {
	AliasSlug     string `json:"alias_slug"`
	CanonicalSlug string `json:"canonical_slug"`
}
type packageImage struct {
	Path, SHA256, MIMEType string `json:"-"`
	Width, Height          int
	Bytes                  int64
	Variants               []packageVariant
}

func (i *packageImage) UnmarshalJSON(raw []byte) error {
	var v struct {
		Path     string           `json:"path"`
		SHA256   string           `json:"sha256"`
		MIMEType string           `json:"mime_type"`
		Width    int              `json:"width"`
		Height   int              `json:"height"`
		Bytes    int64            `json:"bytes"`
		Variants []packageVariant `json:"variants"`
	}
	if err := json.Unmarshal(raw, &v); err != nil {
		return err
	}
	i.Path, i.SHA256, i.MIMEType, i.Width, i.Height, i.Bytes, i.Variants = v.Path, v.SHA256, v.MIMEType, v.Width, v.Height, v.Bytes, v.Variants
	return nil
}

type packageVariant struct {
	Role string `json:"role"`
	packageImage
}

func (v *packageVariant) UnmarshalJSON(raw []byte) error {
	var role struct {
		Role string `json:"role"`
	}
	if err := json.Unmarshal(raw, &role); err != nil {
		return err
	}
	var image packageImage
	if err := json.Unmarshal(raw, &image); err != nil {
		return err
	}
	v.Role, v.packageImage = role.Role, image
	return nil
}

type packageWine struct {
	Slug                 string                `json:"slug"`
	Title                string                `json:"title"`
	Producer             string                `json:"producer"`
	Description          string                `json:"description"`
	Year                 *int                  `json:"vintage_year"`
	SourceURL            string                `json:"source_url"`
	SourceSnapshotDate   string                `json:"source_snapshot_date"`
	Region               []string              `json:"region"`
	Grapes               []string              `json:"grapes"`
	CategoryAndSweetness string                `json:"category_and_sweetness"`
	Color                string                `json:"color_description"`
	Sugar                string                `json:"sweetness"`
	AlcoholPercent       *float64              `json:"alcohol_percent"`
	AlcoholMinPercent    *float64              `json:"alcohol_min_percent"`
	AlcoholMaxPercent    *float64              `json:"alcohol_max_percent"`
	VolumeL              *float64              `json:"volume_l"`
	Ratings              []catalogmodel.Rating `json:"ratings"`
	Image                packageImage          `json:"image"`
	imagePresent         bool
	imageNull            bool
	Variants             []packageVariant `json:"variants"`
}

func (w *packageWine) UnmarshalJSON(raw []byte) error {
	type plain packageWine
	var value plain
	if err := json.Unmarshal(raw, &value); err != nil {
		return err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return err
	}
	image, present := fields["image"]
	value.imagePresent = present
	value.imageNull = present && bytes.Equal(bytes.TrimSpace(image), []byte("null"))
	*w = packageWine(value)
	return nil
}

func Import(ctx context.Context, db *sql.DB, opts Options) (Result, error) {
	wines, aliases, err := Load(opts.PackageDir, opts.Version)
	if err != nil {
		return Result{}, err
	}
	result := Result{Version: opts.Version, Wines: len(wines), Aliases: len(aliases), DryRun: opts.DryRun}
	if opts.DryRun {
		return result, nil
	}
	if err := replace(ctx, db, opts.Version, wines, aliases, fingerprint(wines, aliases)); err != nil {
		return Result{}, err
	}
	return result, nil
}

func Load(packageDir, version string) ([]catalogmodel.Wine, []Alias, error) {
	if version == "" || strings.ContainsAny(version, "/\\") {
		return nil, nil, errors.New("version must be a non-path identifier")
	}
	root, err := filepath.Abs(packageDir)
	if err != nil {
		return nil, nil, err
	}
	public := filepath.Join(root, "public")
	if info, err := os.Lstat(public); err != nil || info.Mode()&os.ModeSymlink != 0 {
		return nil, nil, errors.New("public directory must not be a symlink")
	}
	if info, err := os.Stat(public); err != nil || !info.IsDir() {
		return nil, nil, errors.New("package must contain public directory")
	}
	raw, err := readSafe(public, "wines.json")
	if err != nil {
		raw, err = readSafe(public, "wines.jsonl")
		if err != nil {
			return nil, nil, fmt.Errorf("read wines: %w", err)
		}
	}
	records, err := parseWines(raw)
	if err != nil {
		return nil, nil, fmt.Errorf("parse wines: %w", err)
	}
	if len(records) == 0 {
		return nil, nil, errors.New("catalog has no wines")
	}
	strictV2 := strings.Contains(strings.ToLower(version), "v2")
	wines := make([]catalogmodel.Wine, 0, len(records))
	seen := map[string]bool{}
	for _, r := range records {
		w, err := toWine(public, version, r, strictV2)
		if err != nil {
			return nil, nil, err
		}
		if seen[w.ID] {
			return nil, nil, fmt.Errorf("duplicate slug %q", w.ID)
		}
		seen[w.ID] = true
		wines = append(wines, w)
	}
	aliases, err := loadAliases(public, seen)
	if err != nil {
		return nil, nil, err
	}
	sort.Slice(wines, func(i, j int) bool { return wines[i].ID < wines[j].ID })
	return wines, aliases, nil
}

func parseWines(raw []byte) ([]packageWine, error) {
	var rows []packageWine
	if json.Unmarshal(raw, &rows) == nil {
		return rows, nil
	}
	for _, line := range bytes.Split(raw, []byte{'\n'}) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		var row packageWine
		if err := json.Unmarshal(line, &row); err != nil {
			return nil, err
		}
		rows = append(rows, row)
	}
	return rows, nil
}
func loadAliases(public string, known map[string]bool) ([]Alias, error) {
	raw, err := readSafe(public, "aliases.json")
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var data struct {
		Aliases []Alias `json:"aliases"`
	}
	if err = json.Unmarshal(raw, &data); err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	for _, a := range data.Aliases {
		if a.AliasSlug == "" || a.CanonicalSlug == "" || a.AliasSlug == a.CanonicalSlug || seen[a.AliasSlug] || known[a.AliasSlug] || !known[a.CanonicalSlug] {
			return nil, fmt.Errorf("invalid alias %q", a.AliasSlug)
		}
		seen[a.AliasSlug] = true
	}
	sort.Slice(data.Aliases, func(i, j int) bool { return data.Aliases[i].AliasSlug < data.Aliases[j].AliasSlug })
	return data.Aliases, nil
}
func toWine(public, version string, r packageWine, strictV2 bool) (catalogmodel.Wine, error) {
	if r.Slug == "" || strings.ContainsAny(r.Slug, "/\\") || r.Title == "" || r.Producer == "" {
		return catalogmodel.Wine{}, fmt.Errorf("wine requires safe slug, title and producer")
	}
	if r.Year != nil && (*r.Year < 1000 || *r.Year > time.Now().Year()+1) {
		return catalogmodel.Wine{}, fmt.Errorf("invalid year for %q", r.Slug)
	}
	parsedURL, err := url.Parse(r.SourceURL)
	if err != nil || r.SourceURL == "" || (parsedURL.Scheme != "https" && parsedURL.Scheme != "http") || parsedURL.Host == "" {
		return catalogmodel.Wine{}, fmt.Errorf("invalid source_url for %q", r.Slug)
	}
	sanitizeAlcohol(&r)
	if !r.imagePresent {
		return catalogmodel.Wine{}, fmt.Errorf("%s image must be null or a complete image object", r.Slug)
	}
	var imageURL string
	var master catalogmodel.ImageVariant
	if !r.imageNull {
		var err error
		imageURL, master, err = validateImage(public, version, r.Image, "", strictV2)
		if err != nil {
			return catalogmodel.Wine{}, fmt.Errorf("%s image: %w", r.Slug, err)
		}
	}
	w := catalogmodel.Wine{ID: r.Slug, Name: r.Title, Winery: r.Producer, Description: r.Description, Image: imageURL, SourceURL: r.SourceURL, SourceSnapshotDate: r.SourceSnapshotDate, Region: r.Region, Grapes: r.Grapes, CategoryAndSweetness: r.CategoryAndSweetness, Color: r.Color, Sugar: r.Sugar, AlcoholPercent: r.AlcoholPercent, AlcoholMinPercent: r.AlcoholMinPercent, AlcoholMaxPercent: r.AlcoholMaxPercent, VolumeL: r.VolumeL, Ratings: r.Ratings}
	if r.Year != nil {
		w.Year = *r.Year
	}
	roles := map[string]bool{}
	for _, v := range append(r.Image.Variants, r.Variants...) {
		if r.imageNull {
			return catalogmodel.Wine{}, errors.New("null image cannot have variants")
		}
		if v.Role != "thumbnail" && v.Role != "card" && v.Role != "original" || roles[v.Role] {
			return catalogmodel.Wine{}, fmt.Errorf("invalid image variant role %q", v.Role)
		}
		roles[v.Role] = true
		_, iv, err := validateImage(public, version, v.packageImage, v.Role, strictV2)
		if err != nil {
			return catalogmodel.Wine{}, err
		}
		if iv.Width > master.Width || iv.Height > master.Height || (v.Role == "thumbnail" && iv.Width > 400) || (v.Role == "card" && iv.Width > 800) || (v.Role == "original" && iv.Width > 1600) {
			return catalogmodel.Wine{}, fmt.Errorf("image variant %q exceeds master or role bound", v.Role)
		}
		w.ImageVariants = append(w.ImageVariants, iv)
	}
	if strictV2 && !r.imageNull && !(roles["thumbnail"] && roles["card"] && roles["original"]) {
		return catalogmodel.Wine{}, errors.New("v2 image requires thumbnail, card and original variants")
	}
	return w, nil
}
func sanitizeAlcohol(r *packageWine) {
	for _, p := range []*(*float64){&r.AlcoholPercent, &r.AlcoholMinPercent, &r.AlcoholMaxPercent} {
		if *p != nil && (**p < 0 || **p > 100) {
			*p = nil
		}
	}
	if r.AlcoholMinPercent != nil && r.AlcoholMaxPercent != nil && *r.AlcoholMinPercent > *r.AlcoholMaxPercent {
		r.AlcoholMinPercent, r.AlcoholMaxPercent = nil, nil
	}
	if r.VolumeL != nil && (*r.VolumeL <= 0 || *r.VolumeL > 100) {
		r.VolumeL = nil
	}
}
func validateImage(public, version string, spec packageImage, role string, strictV2 bool) (string, catalogmodel.ImageVariant, error) {
	if strictV2 && (spec.SHA256 == "" || spec.MIMEType == "" || spec.Width < 1 || spec.Height < 1 || spec.Bytes < 1) {
		return "", catalogmodel.ImageVariant{}, errors.New("v2 image metadata is incomplete")
	}
	if spec.Path == "" {
		return "", catalogmodel.ImageVariant{}, errors.New("image path is required")
	}
	data, err := readSafe(public, spec.Path)
	if err != nil {
		return "", catalogmodel.ImageVariant{}, err
	}
	if int64(len(data)) > maxImageBytes {
		return "", catalogmodel.ImageVariant{}, errors.New("image too large")
	}
	sum := sha256.Sum256(data)
	if spec.SHA256 == "" || !strings.EqualFold(spec.SHA256, hex.EncodeToString(sum[:])) {
		return "", catalogmodel.ImageVariant{}, errors.New("image checksum mismatch")
	}
	cfg, format, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		return "", catalogmodel.ImageVariant{}, errors.New("image cannot be decoded")
	}
	mimeType := "image/" + format
	if format == "jpeg" {
		mimeType = "image/jpeg"
	}
	if spec.MIMEType != "" && spec.MIMEType != mimeType {
		return "", catalogmodel.ImageVariant{}, errors.New("image MIME type mismatch")
	}
	if cfg.Width < 1 || cfg.Height < 1 || cfg.Width > maxImageDimension || cfg.Height > maxImageDimension || cfg.Width*cfg.Height > maxImagePixels {
		return "", catalogmodel.ImageVariant{}, errors.New("image dimensions exceed bounds")
	}
	if spec.Width > 0 && spec.Width != cfg.Width || spec.Height > 0 && spec.Height != cfg.Height || spec.Bytes > 0 && spec.Bytes != int64(len(data)) {
		return "", catalogmodel.ImageVariant{}, errors.New("image dimensions or bytes mismatch")
	}
	url := "/catalog-assets/" + version + "/" + filepath.ToSlash(spec.Path)
	return url, catalogmodel.ImageVariant{Role: role, Path: url, Width: cfg.Width, Height: cfg.Height, Bytes: int64(len(data)), MIMEType: mimeType, SHA256: hex.EncodeToString(sum[:])}, nil
}
func readSafe(root, relative string) ([]byte, error) {
	if filepath.IsAbs(relative) || relative == "" {
		return nil, os.ErrNotExist
	}
	clean := filepath.Clean(relative)
	if clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return nil, os.ErrNotExist
	}
	current := root
	for _, part := range strings.Split(clean, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, errors.New("symlink paths are forbidden")
		}
	}
	info, err := os.Stat(current)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("path is not a regular file")
	}
	f, err := os.Open(current)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return io.ReadAll(io.LimitReader(f, maxImageBytes+1))
}

func Export(ctx context.Context, db *sql.DB) (Snapshot, error) {
	var s Snapshot
	err := db.QueryRowContext(ctx, "SELECT version FROM catalog_state WHERE singleton").Scan(&s.Version)
	if err != nil {
		return s, err
	}
	rows, err := db.QueryContext(ctx, "SELECT id,name,winery,year,image,description,metadata FROM demo_catalog ORDER BY display_order")
	if err != nil {
		return s, err
	}
	defer rows.Close()
	for rows.Next() {
		var w catalogmodel.Wine
		var year sql.NullInt64
		var metadata []byte
		if err := rows.Scan(&w.ID, &w.Name, &w.Winery, &year, &w.Image, &w.Description, &metadata); err != nil {
			return s, err
		}
		if year.Valid {
			w.Year = int(year.Int64)
		}
		if err := json.Unmarshal(metadata, &w); err != nil {
			return s, err
		}
		s.Wines = append(s.Wines, w)
	}
	if err = rows.Err(); err != nil {
		return s, err
	}
	a, err := db.QueryContext(ctx, "SELECT alias_slug,canonical_slug FROM catalog_aliases ORDER BY alias_slug")
	if err != nil {
		return s, err
	}
	defer a.Close()
	for a.Next() {
		var x Alias
		if err := a.Scan(&x.AliasSlug, &x.CanonicalSlug); err != nil {
			return s, err
		}
		s.Aliases = append(s.Aliases, x)
	}
	return s, a.Err()
}
func replace(ctx context.Context, db *sql.DB, version string, wines []catalogmodel.Wine, aliases []Alias, packageSHA string) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var active string
	err = tx.QueryRowContext(ctx, "SELECT version FROM catalog_state WHERE singleton FOR UPDATE").Scan(&active)
	if err != nil && err != sql.ErrNoRows {
		return err
	}
	var registered string
	versionErr := tx.QueryRowContext(ctx, "SELECT package_sha256 FROM catalog_versions WHERE version=$1", version).Scan(&registered)
	if versionErr == nil && registered != "" && registered != packageSHA {
		return errors.New("catalog version already exists with different package content")
	}
	if versionErr != nil && versionErr != sql.ErrNoRows {
		return versionErr
	}
	if active == version {
		return nil
	}
	if versionErr == nil && registered == "" {
		if _, err := tx.ExecContext(ctx, "UPDATE catalog_versions SET package_sha256=$1 WHERE version=$2", packageSHA, version); err != nil {
			return err
		}
	}
	if _, err = tx.ExecContext(ctx, "INSERT INTO catalog_versions(version,package_sha256) VALUES($1,$2) ON CONFLICT DO NOTHING", version, packageSHA); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, "DELETE FROM catalog_aliases"); err != nil {
		return err
	}
	if _, err = tx.ExecContext(ctx, "DELETE FROM demo_catalog"); err != nil {
		return err
	}
	for i, w := range wines {
		m, err := metadata(w)
		if err != nil {
			return err
		}
		var year any = nil
		if w.Year > 0 {
			year = w.Year
		}
		if _, err = tx.ExecContext(ctx, "INSERT INTO demo_catalog(id,name,winery,year,image,description,display_order,metadata) VALUES($1,$2,$3,$4,$5,$6,$7,$8)", w.ID, w.Name, w.Winery, year, w.Image, w.Description, i+1, m); err != nil {
			return err
		}
	}
	for _, a := range aliases {
		if _, err = tx.ExecContext(ctx, "INSERT INTO catalog_aliases(alias_slug,canonical_slug) VALUES($1,$2)", a.AliasSlug, a.CanonicalSlug); err != nil {
			return err
		}
	}
	if _, err = tx.ExecContext(ctx, "INSERT INTO catalog_state(singleton,version) VALUES(true,$1) ON CONFLICT(singleton) DO UPDATE SET version=EXCLUDED.version", version); err != nil {
		return err
	}
	return tx.Commit()
}
func fingerprint(wines []catalogmodel.Wine, aliases []Alias) string {
	raw, _ := json.Marshal(struct {
		Wines   []catalogmodel.Wine `json:"wines"`
		Aliases []Alias             `json:"aliases"`
	}{wines, aliases})
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}
func metadata(w catalogmodel.Wine) ([]byte, error) {
	raw, err := json.Marshal(w)
	if err != nil {
		return nil, err
	}
	var m map[string]any
	if err = json.Unmarshal(raw, &m); err != nil {
		return nil, err
	}
	for _, key := range []string{"id", "name", "winery", "year", "image", "description"} {
		delete(m, key)
	}
	return json.Marshal(m)
}

// Restore validates the saved snapshot before atomically making it active.
func Restore(ctx context.Context, db *sql.DB, snapshot Snapshot) error {
	if snapshot.Version == "" || len(snapshot.Wines) == 0 {
		return errors.New("invalid snapshot")
	}
	seen := make(map[string]bool, len(snapshot.Wines))
	for _, wine := range snapshot.Wines {
		if wine.ID == "" || seen[wine.ID] {
			return errors.New("invalid snapshot wines")
		}
		seen[wine.ID] = true
	}
	for _, alias := range snapshot.Aliases {
		if alias.AliasSlug == "" || !seen[alias.CanonicalSlug] {
			return errors.New("invalid snapshot aliases")
		}
	}
	return replace(ctx, db, snapshot.Version, snapshot.Wines, snapshot.Aliases, fingerprint(snapshot.Wines, snapshot.Aliases))
}
