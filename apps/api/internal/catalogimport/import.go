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
	"io/fs"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
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
	MediaRoot  string
	Version    string
	DryRun     bool
}

type Result struct {
	Version        string
	Wines, Aliases int
	DryRun         bool
	ManifestSHA256 string
}

type Snapshot struct {
	Version        string              `json:"version"`
	ManifestSHA256 string              `json:"manifestSHA256"`
	Wines          []catalogmodel.Wine `json:"wines"`
	Aliases        []Alias             `json:"aliases"`
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
	ID                   string                `json:"id"`
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
	wines, aliases, manifestSHA, err := load(opts.PackageDir, opts.MediaRoot, opts.Version)
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

func Load(packageDir, version string) ([]catalogmodel.Wine, []Alias, error) {
	wines, aliases, _, err := load(packageDir, "", version)
	return wines, aliases, err
}

type releaseManifest struct {
	SchemaVersion  string `json:"schema_version"`
	CatalogVersion string `json:"catalog_version"`
	Files          []struct {
		Path   string `json:"path"`
		SHA256 string `json:"sha256"`
		Bytes  int64  `json:"bytes"`
	} `json:"files"`
	Media []struct {
		Path     string `json:"path"`
		SHA256   string `json:"sha256"`
		Bytes    int64  `json:"bytes"`
		Width    int    `json:"width"`
		Height   int    `json:"height"`
		MIMEType string `json:"mime_type"`
	} `json:"media"`
}

func loadRelease(root, mediaRoot, version string, rawManifest []byte) ([]catalogmodel.Wine, []Alias, string, error) {
	var manifest releaseManifest
	if err := json.Unmarshal(rawManifest, &manifest); err != nil {
		return nil, nil, "", fmt.Errorf("parse manifest: %w", err)
	}
	if mediaRoot == "" {
		mediaRoot = filepath.Join(filepath.Dir(filepath.Dir(root)), "media")
	}
	if manifest.SchemaVersion != "catalog-release-1" || manifest.CatalogVersion != version {
		return nil, nil, "", errors.New("release requires catalog-release-1 manifest and matching version")
	}
	requiredFiles := map[string]bool{"wines.jsonl": false, "aliases.json": false, "catalog.json": false, "internal/display-policy.json": false, "PREPARATION.md": false}
	for _, f := range manifest.Files {
		if _, ok := requiredFiles[f.Path]; !ok || requiredFiles[f.Path] {
			return nil, nil, "", fmt.Errorf("invalid or duplicate manifest file %q", f.Path)
		}
		requiredFiles[f.Path] = true
		data, err := readSafe(root, f.Path)
		if err != nil {
			return nil, nil, "", fmt.Errorf("manifest file %s: %w", f.Path, err)
		}
		if f.Bytes != int64(len(data)) || !matchesSHA(data, f.SHA256) {
			return nil, nil, "", fmt.Errorf("manifest file %s digest or bytes mismatch", f.Path)
		}
	}
	for path, found := range requiredFiles {
		if !found {
			return nil, nil, "", fmt.Errorf("manifest missing required file %s", path)
		}
	}
	if err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return errors.New("release symlink is forbidden")
		}
		if entry.IsDir() {
			return nil
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		if rel != "manifest.json" && !requiredFiles[filepath.ToSlash(rel)] {
			return fmt.Errorf("release file %s is not in manifest", rel)
		}
		return nil
	}); err != nil {
		return nil, nil, "", err
	}
	seenMedia := map[string]bool{}
	for _, f := range manifest.Media {
		if seenMedia[f.Path] || !validMediaKey(f.Path, f.SHA256) {
			return nil, nil, "", fmt.Errorf("invalid manifest media path %q", f.Path)
		}
		seenMedia[f.Path] = true
		data, err := readSafe(mediaRoot, f.Path)
		if err != nil {
			return nil, nil, "", fmt.Errorf("manifest media %s: %w", f.Path, err)
		}
		if f.Bytes != int64(len(data)) || !matchesSHA(data, f.SHA256) {
			return nil, nil, "", fmt.Errorf("manifest media %s digest or bytes mismatch", f.Path)
		}
		_, actual, err := validateImage(mediaRoot, version, packageImage{Path: f.Path, SHA256: f.SHA256, MIMEType: f.MIMEType, Width: f.Width, Height: f.Height, Bytes: f.Bytes}, "", true, true)
		if err != nil || actual.MIMEType != "image/webp" {
			return nil, nil, "", fmt.Errorf("manifest media %s is not valid WebP: %v", f.Path, err)
		}
	}
	catalog, err := readSafe(root, "catalog.json")
	if err != nil {
		return nil, nil, "", err
	}
	var policy struct {
		SchemaVersion string `json:"schema_version"`
	}
	if json.Unmarshal(catalog, &policy) != nil || policy.SchemaVersion != "svoe-display-catalog-2.0.0" {
		return nil, nil, "", errors.New("catalog.json requires schema_version svoe-display-catalog-2.0.0")
	}
	raw, err := readSafe(root, "wines.jsonl")
	if err != nil {
		return nil, nil, "", err
	}
	if err := validateDisplayPolicy(root, raw); err != nil {
		return nil, nil, "", err
	}
	records, err := parseWines(raw)
	if err != nil || len(records) == 0 {
		return nil, nil, "", errors.New("release has no valid wines")
	}
	wines := make([]catalogmodel.Wine, 0, len(records))
	ids, slugs := map[string]bool{}, map[string]bool{}
	for _, r := range records {
		if r.ID == "" {
			return nil, nil, "", errors.New("release wine requires stable id")
		}
		w, err := toWine(mediaRoot, version, r, true)
		if err != nil {
			return nil, nil, "", err
		}
		if w.ID == "" || ids[w.ID] || slugs[w.Slug] {
			return nil, nil, "", fmt.Errorf("duplicate catalog id or slug %q", w.ID)
		}
		ids[w.ID], slugs[w.Slug] = true, true
		if w.Image == "" || !seenMedia[w.Image] || len(w.ImageVariants) != 3 {
			return nil, nil, "", fmt.Errorf("%s requires all display image roles", w.Slug)
		}
		for _, v := range w.ImageVariants {
			roleDir := map[string]string{"thumbnail": "400", "card": "800", "original": "original"}[v.Role]
			if !seenMedia[v.Path] || !strings.HasPrefix(v.Path, roleDir+"/") {
				return nil, nil, "", fmt.Errorf("%s references unmanifested media %s", w.Slug, v.Path)
			}
		}
		wines = append(wines, w)
	}
	aliases, err := loadAliases(root, slugs)
	if err != nil {
		return nil, nil, "", err
	}
	sort.Slice(wines, func(i, j int) bool { return wines[i].ID < wines[j].ID })
	sum := sha256.Sum256(rawManifest)
	return wines, aliases, hex.EncodeToString(sum[:]), nil
}
func validateDisplayPolicy(root string, wines []byte) error {
	raw, err := readSafe(root, "internal/display-policy.json")
	if err != nil {
		return err
	}
	var policy struct {
		SchemaVersion     string `json:"schema_version"`
		SourceManifestSHA string `json:"source_manifest_sha256"`
		Suppressed        []struct {
			Slug  string `json:"slug"`
			Field string `json:"field"`
		} `json:"suppressed_fields"`
	}
	if json.Unmarshal(raw, &policy) != nil || policy.SchemaVersion != "catalog-display-policy-1" || policy.SourceManifestSHA == "" {
		return errors.New("invalid display policy")
	}
	rows := map[string]map[string]any{}
	for _, line := range bytes.Split(wines, []byte{'\n'}) {
		if len(bytes.TrimSpace(line)) == 0 {
			continue
		}
		var row map[string]any
		if json.Unmarshal(line, &row) != nil {
			return errors.New("invalid wines JSONL")
		}
		slug, _ := row["slug"].(string)
		rows[slug] = row
	}
	for _, rule := range policy.Suppressed {
		row := rows[rule.Slug]
		if row == nil || hasField(row, strings.Split(rule.Field, ".")) {
			return fmt.Errorf("suppressed field %s remains on %s", rule.Field, rule.Slug)
		}
	}
	return nil
}
func hasField(row map[string]any, parts []string) bool {
	var cur any = row
	for _, part := range parts {
		m, ok := cur.(map[string]any)
		if !ok {
			return false
		}
		v, ok := m[part]
		if !ok {
			return false
		}
		cur = v
	}
	return true
}
func matchesSHA(data []byte, expected string) bool {
	sum := sha256.Sum256(data)
	return expected != "" && strings.EqualFold(expected, hex.EncodeToString(sum[:]))
}
func validMediaKey(path, sha string) bool {
	parts := strings.Split(path, "/")
	if len(parts) != 2 || (parts[0] != "400" && parts[0] != "800" && parts[0] != "original") || len(parts[1]) != 69 || !strings.HasSuffix(parts[1], ".webp") {
		return false
	}
	name := strings.TrimSuffix(parts[1], ".webp")
	if name != strings.ToLower(name) {
		return false
	}
	decoded, err := hex.DecodeString(name)
	return err == nil && len(decoded) == sha256.Size && strings.EqualFold(name, sha)
}

// load accepts the old offline source v2 public/ package and the installed
// catalog-release-1 layout. The latter always has an explicit manifest.
func load(packageDir, mediaRoot, version string) ([]catalogmodel.Wine, []Alias, string, error) {
	if version == "" || strings.ContainsAny(version, "/\\") {
		return nil, nil, "", errors.New("version must be a non-path identifier")
	}
	root, err := filepath.Abs(packageDir)
	if err != nil {
		return nil, nil, "", err
	}
	if raw, err := readSafe(root, "manifest.json"); err == nil {
		return loadRelease(root, mediaRoot, version, raw)
	}
	public := filepath.Join(root, "public")
	if info, err := os.Lstat(public); err != nil || info.Mode()&os.ModeSymlink != 0 {
		return nil, nil, "", errors.New("public directory must not be a symlink")
	}
	if info, err := os.Stat(public); err != nil || !info.IsDir() {
		return nil, nil, "", errors.New("package must contain public directory")
	}
	raw, err := readSafe(public, "wines.json")
	if err != nil {
		raw, err = readSafe(public, "wines.jsonl")
		if err != nil {
			return nil, nil, "", fmt.Errorf("read wines: %w", err)
		}
	}
	records, err := parseWines(raw)
	if err != nil {
		return nil, nil, "", fmt.Errorf("parse wines: %w", err)
	}
	if len(records) == 0 {
		return nil, nil, "", errors.New("catalog has no wines")
	}
	strictV2 := strings.Contains(strings.ToLower(version), "v2")
	wines := make([]catalogmodel.Wine, 0, len(records))
	seen := map[string]bool{}
	for _, r := range records {
		w, err := toWine(public, version, r, strictV2)
		if err != nil {
			return nil, nil, "", err
		}
		if seen[w.Slug] {
			return nil, nil, "", fmt.Errorf("duplicate slug %q", w.Slug)
		}
		seen[w.Slug] = true
		wines = append(wines, w)
	}
	aliases, err := loadAliases(public, seen)
	if err != nil {
		return nil, nil, "", err
	}
	sort.Slice(wines, func(i, j int) bool { return wines[i].ID < wines[j].ID })
	return wines, aliases, fingerprint(wines, aliases), nil
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
	if r.Slug == "" || strings.ContainsAny(r.Slug, "/\\") || (r.ID != "" && strings.ContainsAny(r.ID, "/\\")) || r.Title == "" || r.Producer == "" {
		return catalogmodel.Wine{}, fmt.Errorf("wine requires safe slug, title and producer")
	}
	if r.Year != nil && (*r.Year < 1000 || *r.Year > time.Now().Year()+1) {
		return catalogmodel.Wine{}, fmt.Errorf("invalid year for %q", r.Slug)
	}
	parsedURL, err := url.Parse(r.SourceURL)
	if r.SourceURL != "" && (err != nil || (parsedURL.Scheme != "https" && parsedURL.Scheme != "http") || parsedURL.Host == "") {
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
		imageURL, master, err = validateImage(public, version, r.Image, "", strictV2, false)
		if err != nil {
			return catalogmodel.Wine{}, fmt.Errorf("%s image: %w", r.Slug, err)
		}
	}
	id := r.ID
	if id == "" {
		id = r.Slug
	}
	w := catalogmodel.Wine{ID: id, Slug: r.Slug, Name: r.Title, Winery: r.Producer, Description: r.Description, Image: imageURL, SourceURL: r.SourceURL, SourceSnapshotDate: r.SourceSnapshotDate, Region: r.Region, Grapes: r.Grapes, CategoryAndSweetness: r.CategoryAndSweetness, Color: r.Color, Sugar: r.Sugar, AlcoholPercent: r.AlcoholPercent, AlcoholMinPercent: r.AlcoholMinPercent, AlcoholMaxPercent: r.AlcoholMaxPercent, VolumeL: r.VolumeL, Ratings: r.Ratings}
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
		_, iv, err := validateImage(public, version, v.packageImage, v.Role, strictV2, false)
		if err != nil {
			return catalogmodel.Wine{}, err
		}
		if err := validateVariantGeometry(master, iv); err != nil {
			return catalogmodel.Wine{}, fmt.Errorf("image variant %q: %w", v.Role, err)
		}
		if (v.Role == "thumbnail" && maxSide(iv.Width, iv.Height) > 400) || (v.Role == "card" && maxSide(iv.Width, iv.Height) > 800) || (v.Role == "original" && maxSide(iv.Width, iv.Height) > 1600) {
			return catalogmodel.Wine{}, fmt.Errorf("image variant %q exceeds master or role bound", v.Role)
		}
		w.ImageVariants = append(w.ImageVariants, iv)
	}
	if !r.imageNull && maxSide(master.Width, master.Height) > 1600 {
		return catalogmodel.Wine{}, errors.New("master image exceeds long-side bound")
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
func validateImage(public, version string, spec packageImage, role string, strictV2, fullDecode bool) (string, catalogmodel.ImageVariant, error) {
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
	// DecodeConfig accepts malformed bodies with a valid header. Decode the
	// bounded input completely before accepting a public media reference.
	if fullDecode {
		decoded, _, err := image.Decode(bytes.NewReader(data))
		if err != nil || decoded.Bounds().Dx() != cfg.Width || decoded.Bounds().Dy() != cfg.Height {
			return "", catalogmodel.ImageVariant{}, errors.New("image cannot be fully decoded")
		}
	}
	if spec.Width > 0 && spec.Width != cfg.Width || spec.Height > 0 && spec.Height != cfg.Height || spec.Bytes > 0 && spec.Bytes != int64(len(data)) {
		return "", catalogmodel.ImageVariant{}, errors.New("image dimensions or bytes mismatch")
	}
	key := filepath.ToSlash(spec.Path)
	return key, catalogmodel.ImageVariant{Role: role, Path: key, Width: cfg.Width, Height: cfg.Height, Bytes: int64(len(data)), MIMEType: mimeType, SHA256: hex.EncodeToString(sum[:])}, nil
}
func maxSide(width, height int) int {
	if width > height {
		return width
	}
	return height
}

func validateVariantGeometry(master, variant catalogmodel.ImageVariant) error {
	if variant.Width > master.Width || variant.Height > master.Height {
		return errors.New("upscales the master image")
	}
	// Encoders may round a scaled dimension by one pixel. Cross multiplication
	// keeps the comparison deterministic without floating-point ratios.
	delta := variant.Width*master.Height - variant.Height*master.Width
	if delta < 0 {
		delta = -delta
	}
	tolerance := max(master.Width, master.Height)
	if delta > tolerance {
		return errors.New("aspect ratio differs from the master image")
	}
	return nil
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
	var stateTable, itemTable sql.NullString
	if err := db.QueryRowContext(ctx, "SELECT to_regclass('public.catalog_state')::text, to_regclass('public.catalog_items')::text").Scan(&stateTable, &itemTable); err != nil {
		return Snapshot{}, err
	}
	if !stateTable.Valid || !itemTable.Valid {
		return exportLegacy(ctx, db)
	}
	return export(ctx, db)
}

func exportLegacy(ctx context.Context, db snapshotQuerier) (Snapshot, error) {
	s := Snapshot{Version: "demo-v1", Aliases: []Alias{}}
	rows, err := db.QueryContext(ctx, "SELECT id,name,winery,year,image,description FROM demo_catalog ORDER BY display_order")
	if err != nil {
		return s, err
	}
	defer rows.Close()
	for rows.Next() {
		var w catalogmodel.Wine
		if err := rows.Scan(&w.ID, &w.Name, &w.Winery, &w.Year, &w.Image, &w.Description); err != nil {
			return s, err
		}
		w.Slug = w.ID
		s.Wines = append(s.Wines, w)
	}
	if err := rows.Err(); err != nil {
		return s, err
	}
	if len(s.Wines) == 0 {
		return s, errors.New("legacy catalog snapshot has no wines")
	}
	s.ManifestSHA256 = fingerprint(s.Wines, nil)
	return s, nil
}

type snapshotQuerier interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
	QueryContext(context.Context, string, ...any) (*sql.Rows, error)
}

func export(ctx context.Context, db snapshotQuerier) (Snapshot, error) {
	s := Snapshot{Aliases: []Alias{}}
	err := db.QueryRowContext(ctx, `SELECT s.version, v.package_sha256
		FROM catalog_state s JOIN catalog_versions v ON v.version=s.version
		WHERE s.singleton`).Scan(&s.Version, &s.ManifestSHA256)
	if err != nil {
		return s, err
	}
	rows, err := db.QueryContext(ctx, "SELECT id,slug,name,winery,year,image,description,metadata FROM catalog_items ORDER BY display_order")
	if err != nil {
		return s, err
	}
	defer rows.Close()
	for rows.Next() {
		var w catalogmodel.Wine
		var year sql.NullInt64
		var metadata []byte
		if err := rows.Scan(&w.ID, &w.Slug, &w.Name, &w.Winery, &year, &w.Image, &w.Description, &metadata); err != nil {
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
	if err := a.Err(); err != nil {
		return s, err
	}
	if s.ManifestSHA256 == "" {
		s.ManifestSHA256 = fingerprint(s.Wines, s.Aliases)
	}
	return s, nil
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
		actual, exportErr := export(ctx, tx)
		if exportErr != nil {
			return exportErr
		}
		if actual.ManifestSHA256 != packageSHA || !equalProjection(actual, wines, aliases) {
			return errors.New("active catalog version content differs from requested package")
		}
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
	if _, err = tx.ExecContext(ctx, "DELETE FROM catalog_items"); err != nil {
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
		if _, err = tx.ExecContext(ctx, "INSERT INTO catalog_items(id,slug,name,winery,year,image,description,display_order,metadata) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)", w.ID, w.Slug, w.Name, w.Winery, year, w.Image, w.Description, i+1, m); err != nil {
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
	for _, key := range []string{"id", "slug", "name", "winery", "year", "image", "description"} {
		delete(m, key)
	}
	return json.Marshal(m)
}

// Restore validates the saved snapshot before atomically making it active.
func Restore(ctx context.Context, db *sql.DB, snapshot Snapshot) error {
	if snapshot.Version == "" || snapshot.ManifestSHA256 == "" || len(snapshot.Wines) == 0 {
		return errors.New("invalid snapshot")
	}
	ids := make(map[string]bool, len(snapshot.Wines))
	slugs := make(map[string]bool, len(snapshot.Wines))
	for _, wine := range snapshot.Wines {
		if wine.ID == "" || wine.Slug == "" || ids[wine.ID] || slugs[wine.Slug] {
			return errors.New("invalid snapshot wines")
		}
		ids[wine.ID], slugs[wine.Slug] = true, true
	}
	aliases := make(map[string]bool, len(snapshot.Aliases))
	for _, alias := range snapshot.Aliases {
		if alias.AliasSlug == "" || aliases[alias.AliasSlug] || slugs[alias.AliasSlug] || !slugs[alias.CanonicalSlug] {
			return errors.New("invalid snapshot aliases")
		}
		aliases[alias.AliasSlug] = true
	}
	return replace(ctx, db, snapshot.Version, snapshot.Wines, snapshot.Aliases, snapshot.ManifestSHA256)
}

func equalProjection(snapshot Snapshot, wines []catalogmodel.Wine, aliases []Alias) bool {
	return reflect.DeepEqual(snapshot.Wines, wines) && reflect.DeepEqual(snapshot.Aliases, aliases)
}
