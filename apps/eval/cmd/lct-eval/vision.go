package main

import (
	"bufio"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"slices"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Vision images are independent of the sealed evaluation suite and its gold.
// Only these explicitly named fields are returned by the data API.
type visionImage struct {
	ID                  string          `json:"image_id"`
	Slug                string          `json:"slug,omitempty"`
	Role                string          `json:"role"`
	Path                string          `json:"path"`
	ThumbnailPath       string          `json:"thumbnail_path"`
	Origin              string          `json:"origin"`
	ScenarioIDs         []string        `json:"scenario_ids,omitempty"`
	IdentityReferenceID string          `json:"identity_reference_id,omitempty"`
	SceneReferenceID    string          `json:"scene_reference_id,omitempty"`
	RequestedConditions json.RawMessage `json:"requested_conditions,omitempty"`
	ObservedConditions  json.RawMessage `json:"observed_conditions,omitempty"`
	Model               string          `json:"model,omitempty"`
	Provider            string          `json:"provider,omitempty"`
	CostUSD             float64         `json:"cost_usd,omitempty"`
	LatencyMS           int64           `json:"latency_ms,omitempty"`
	QC                  visionQC        `json:"qc"`
	Split               string          `json:"split,omitempty"`
	ParentIDs           []string        `json:"parent_ids,omitempty"`
	Source              json.RawMessage `json:"source,omitempty"`
	SHA256              string          `json:"sha256,omitempty"`
	SourceGroup         string          `json:"source_group,omitempty"`
}

type visionQC struct {
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

type visionSnapshot struct {
	images []visionImage
	byID   map[string]visionImage
}

type visionCatalog struct {
	root string
	mu   sync.RWMutex
	mod  time.Time
	size int64
	data *visionSnapshot
	err  error
}

func sameOrNestedRoot(one, other string) bool {
	a, ea := canonicalVisionRoot(one)
	b, eb := canonicalVisionRoot(other)
	if ea != nil || eb != nil {
		return true
	}
	for _, pair := range [][2]string{{a, b}, {b, a}} {
		rel, e := filepath.Rel(pair[0], pair[1])
		if e == nil && (rel == "." || rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))) {
			return true
		}
	}
	return false
}

func canonicalVisionRoot(name string) (string, error) {
	abs, e := filepath.Abs(name)
	if e != nil {
		return "", e
	}
	var missing []string
	for {
		resolved, e := filepath.EvalSymlinks(abs)
		if e == nil {
			for i := len(missing) - 1; i >= 0; i-- {
				resolved = filepath.Join(resolved, missing[i])
			}
			return resolved, nil
		}
		if !errors.Is(e, os.ErrNotExist) {
			return "", e
		}
		parent := filepath.Dir(abs)
		if parent == abs {
			return "", e
		}
		missing = append(missing, filepath.Base(abs))
		abs = parent
	}
}

func localImagePath(root, name string) (string, error) {
	if name == "" || strings.ContainsAny(name, "\\\x00") || strings.HasPrefix(name, "/") || path.Clean(name) != name {
		return "", fmt.Errorf("invalid image path %q", name)
	}
	for _, segment := range strings.Split(name, "/") {
		if segment == "" || segment == "." || segment == ".." || segment == "private" {
			return "", fmt.Errorf("invalid image path %q", name)
		}
	}
	switch strings.ToLower(path.Ext(name)) {
	case ".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif":
	default:
		return "", fmt.Errorf("unsupported image extension %q", name)
	}
	current := root
	for _, segment := range strings.Split(name, "/") {
		current = filepath.Join(current, segment)
		info, e := os.Lstat(current)
		if errors.Is(e, os.ErrNotExist) {
			// An in-progress manifest can name an image that has not been copied yet.
			continue
		}
		if e != nil {
			return "", e
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("symlink in image path %q", name)
		}
	}
	return current, nil
}

func validateVisionImage(root string, v *visionImage) error {
	if v.ID == "" || len(v.ID) > 200 || strings.ContainsAny(v.ID, "/\\\x00") {
		return errors.New("invalid image_id")
	}
	if v.Role != "scene_reference" && v.Slug == "" {
		return fmt.Errorf("image %s has no slug", v.ID)
	}
	if len(v.Slug) > 250 || strings.ContainsAny(v.Slug, "/\\\x00") {
		return fmt.Errorf("image %s has invalid slug", v.ID)
	}
	if !slices.Contains([]string{"identity_reference", "scene_reference", "output", "augmentation"}, v.Role) {
		return fmt.Errorf("image %s has invalid role", v.ID)
	}
	if !slices.Contains([]string{"real", "augmentation", "ai_edited", "ai_generated"}, v.Origin) {
		return fmt.Errorf("image %s has invalid origin", v.ID)
	}
	if !slices.Contains([]string{"", "accepted", "rejected", "pending"}, v.QC.Status) {
		return fmt.Errorf("image %s has invalid qc status", v.ID)
	}
	if v.CostUSD < 0 || v.LatencyMS < 0 {
		return fmt.Errorf("image %s has negative cost or latency", v.ID)
	}
	if v.SHA256 != "" {
		digest, e := hex.DecodeString(v.SHA256)
		if e != nil || len(digest) != 32 {
			return fmt.Errorf("image %s has invalid sha256", v.ID)
		}
	}
	if _, e := localImagePath(root, v.Path); e != nil {
		return e
	}
	if v.ThumbnailPath != "" {
		if _, e := localImagePath(root, v.ThumbnailPath); e != nil {
			return e
		}
	}
	v.Source = safeVisionSource(v.Source)
	return nil
}

func safeVisionSource(raw json.RawMessage) json.RawMessage {
	var input struct {
		URL           string `json:"url"`
		Title         string `json:"title"`
		License       string `json:"license"`
		Attribution   string `json:"attribution"`
		SourceID      string `json:"source_id"`
		ProductID     string `json:"product_id"`
		AssociationID string `json:"association_id"`
		MediaID       string `json:"media_id"`
		AssetGroupID  string `json:"asset_group_id"`
	}
	if json.Unmarshal(raw, &input) != nil {
		return nil
	}
	output := map[string]string{}
	if u, e := url.Parse(input.URL); e == nil && u.Scheme == "https" && u.Hostname() != "" && u.User == nil {
		output["url"] = u.String()
	}
	for key, value := range map[string]string{"title": input.Title, "license": input.License, "attribution": input.Attribution, "source_id": input.SourceID, "product_id": input.ProductID, "association_id": input.AssociationID, "media_id": input.MediaID, "asset_group_id": input.AssetGroupID} {
		if value != "" {
			output[key] = value
		}
	}
	if len(output) == 0 {
		return nil
	}
	b, _ := json.Marshal(output)
	return b
}

func readVisionManifest(root string) (*visionSnapshot, error) {
	if info, e := os.Stat(root); e != nil || !info.IsDir() {
		return nil, fmt.Errorf("vision data root unavailable: %v", e)
	}
	manifest := filepath.Join(root, "manifest.jsonl")
	if info, e := os.Lstat(manifest); e == nil && info.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("vision manifest is a symlink")
	}
	f, e := os.Open(manifest)
	if errors.Is(e, os.ErrNotExist) {
		return &visionSnapshot{byID: map[string]visionImage{}}, nil
	}
	if e != nil {
		return nil, e
	}
	defer f.Close()
	result := &visionSnapshot{byID: map[string]visionImage{}}
	scan := bufio.NewScanner(f)
	scan.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for line := 1; scan.Scan(); line++ {
		if len(strings.TrimSpace(scan.Text())) == 0 {
			continue
		}
		var v visionImage
		if e := json.Unmarshal(scan.Bytes(), &v); e != nil {
			return nil, fmt.Errorf("manifest line %d: %w", line, e)
		}
		if e := validateVisionImage(root, &v); e != nil {
			return nil, fmt.Errorf("manifest line %d: %w", line, e)
		}
		if _, exists := result.byID[v.ID]; exists {
			return nil, fmt.Errorf("manifest line %d: duplicate image_id %q", line, v.ID)
		}
		result.images = append(result.images, v)
		result.byID[v.ID] = v
	}
	if e := scan.Err(); e != nil {
		return nil, e
	}
	for _, v := range result.images {
		for _, ref := range append(append([]string{}, v.IdentityReferenceID, v.SceneReferenceID), v.ParentIDs...) {
			if ref != "" {
				if _, ok := result.byID[ref]; !ok {
					return nil, fmt.Errorf("image %s refers to unknown image_id %s", v.ID, ref)
				}
			}
		}
	}
	return result, nil
}

func (c *visionCatalog) snapshot() (*visionSnapshot, error) {
	manifest := filepath.Join(c.root, "manifest.jsonl")
	info, err := os.Stat(manifest)
	if errors.Is(err, os.ErrNotExist) {
		info = nil
		err = nil
	}
	if err != nil {
		return nil, err
	}
	var mod time.Time
	var size int64
	if info != nil {
		mod, size = info.ModTime(), info.Size()
	}
	c.mu.RLock()
	if c.data != nil && c.mod.Equal(mod) && c.size == size {
		data, cachedErr := c.data, c.err
		c.mu.RUnlock()
		return data, cachedErr
	}
	c.mu.RUnlock()
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.data != nil && c.mod.Equal(mod) && c.size == size {
		return c.data, c.err
	}
	c.data, c.err = readVisionManifest(c.root)
	c.mod, c.size = mod, size
	return c.data, c.err
}

func (a *app) visionData(w http.ResponseWriter, r *http.Request) *visionSnapshot {
	if a.vision == nil {
		http.Error(w, "vision data is not configured", http.StatusServiceUnavailable)
		return nil
	}
	data, e := a.vision.snapshot()
	if e != nil {
		http.Error(w, "vision manifest unavailable", http.StatusServiceUnavailable)
		return nil
	}
	return data
}

type visionFilter struct {
	slug, scenario, origin, model, qc, role, split, search string
}

func filterFrom(r *http.Request) visionFilter {
	q := r.URL.Query()
	return visionFilter{q.Get("slug"), q.Get("scenario"), q.Get("origin"), q.Get("model"), q.Get("qc"), q.Get("role"), q.Get("split"), q.Get("q")}
}

func (f visionFilter) matches(v visionImage) bool {
	return (f.slug == "" || v.Slug == f.slug) &&
		(f.scenario == "" || slices.Contains(v.ScenarioIDs, f.scenario)) &&
		(f.origin == "" || v.Origin == f.origin) &&
		(f.model == "" || v.Model == f.model) &&
		(f.qc == "" || v.QC.Status == f.qc) &&
		(f.role == "" || v.Role == f.role) &&
		(f.split == "" || v.Split == f.split) &&
		(f.search == "" || strings.Contains(strings.ToLower(v.Slug), strings.ToLower(f.search)))
}

func pagination(r *http.Request) (page, perPage int, err error) {
	page, perPage = 1, 24
	if s := r.URL.Query().Get("page"); s != "" {
		page, err = strconv.Atoi(s)
		if err != nil || page < 1 || page > 1000000 {
			return 0, 0, errors.New("invalid page")
		}
	}
	if s := r.URL.Query().Get("per_page"); s != "" {
		perPage, err = strconv.Atoi(s)
		if err != nil || perPage < 1 || perPage > 100 {
			return 0, 0, errors.New("invalid per_page (1-100)")
		}
	}
	return page, perPage, nil
}

func pageSlice[T any](all []T, page, perPage int) []T {
	start := (page - 1) * perPage
	if start >= len(all) {
		return []T{}
	}
	end := min(start+perPage, len(all))
	return all[start:end]
}

type slugSummary struct {
	Slug    string         `json:"slug"`
	Total   int            `json:"total"`
	Roles   map[string]int `json:"roles"`
	Origins map[string]int `json:"origins"`
	QC      map[string]int `json:"qc"`
	CostUSD float64        `json:"cost_usd"`
}

func (a *app) dataFacets(w http.ResponseWriter, r *http.Request) {
	data := a.visionData(w, r)
	if data == nil {
		return
	}
	sets := map[string]map[string]bool{
		"scenarios": {}, "origins": {}, "models": {}, "qc": {}, "roles": {}, "splits": {},
	}
	for _, v := range data.images {
		for _, scenario := range v.ScenarioIDs {
			sets["scenarios"][scenario] = true
		}
		for key, value := range map[string]string{"origins": v.Origin, "models": v.Model, "qc": v.QC.Status, "roles": v.Role, "splits": v.Split} {
			if value != "" {
				sets[key][value] = true
			}
		}
	}
	out := map[string][]string{}
	for key, values := range sets {
		out[key] = []string{}
		for value := range values {
			out[key] = append(out[key], value)
		}
		sort.Strings(out[key])
	}
	jsonOut(w, 200, out)
}

func (a *app) dataSlugs(w http.ResponseWriter, r *http.Request) {
	data := a.visionData(w, r)
	if data == nil {
		return
	}
	page, perPage, e := pagination(r)
	if e != nil {
		http.Error(w, e.Error(), 400)
		return
	}
	groups := map[string]*slugSummary{}
	imageCount := 0
	filter := filterFrom(r)
	for _, v := range data.images {
		if v.Slug == "" || !filter.matches(v) {
			continue
		}
		imageCount++
		g := groups[v.Slug]
		if g == nil {
			g = &slugSummary{Slug: v.Slug, Roles: map[string]int{}, Origins: map[string]int{}, QC: map[string]int{}}
			groups[v.Slug] = g
		}
		g.Total++
		g.Roles[v.Role]++
		g.Origins[v.Origin]++
		g.QC[v.QC.Status]++
		g.CostUSD += v.CostUSD
	}
	items := make([]slugSummary, 0, len(groups))
	for _, group := range groups {
		items = append(items, *group)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].Slug < items[j].Slug })
	jsonOut(w, 200, map[string]any{"items": pageSlice(items, page, perPage), "total_slugs": len(items), "total_images": imageCount, "page": page, "per_page": perPage})
}

func (a *app) dataImages(w http.ResponseWriter, r *http.Request) {
	data := a.visionData(w, r)
	if data == nil {
		return
	}
	filter := filterFrom(r)
	if filter.slug == "" {
		http.Error(w, "slug is required", 400)
		return
	}
	page, perPage, e := pagination(r)
	if e != nil {
		http.Error(w, e.Error(), 400)
		return
	}
	items := make([]visionImage, 0)
	for _, v := range data.images {
		if filter.matches(v) {
			items = append(items, v)
		}
	}
	sort.Slice(items, func(i, j int) bool { return items[i].ID < items[j].ID })
	jsonOut(w, 200, map[string]any{"items": pageSlice(items, page, perPage), "total_images": len(items), "page": page, "per_page": perPage})
}

func (a *app) dataImageInfo(w http.ResponseWriter, r *http.Request) {
	data := a.visionData(w, r)
	if data == nil {
		return
	}
	v, ok := data.byID[r.PathValue("id")]
	if !ok {
		http.NotFound(w, r)
		return
	}
	jsonOut(w, 200, v)
}

func (a *app) serveVisionFile(w http.ResponseWriter, r *http.Request, thumbnail bool) {
	data := a.visionData(w, r)
	if data == nil {
		return
	}
	v, ok := data.byID[r.PathValue("id")]
	if !ok {
		http.NotFound(w, r)
		return
	}
	name := v.Path
	if thumbnail {
		name = v.ThumbnailPath
	}
	if name == "" {
		http.NotFound(w, r)
		return
	}
	filePath, e := localImagePath(a.vision.root, name)
	if e != nil {
		http.NotFound(w, r)
		return
	}
	f, e := os.Open(filePath)
	if e != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	info, e := f.Stat()
	if e != nil || !info.Mode().IsRegular() {
		http.NotFound(w, r)
		return
	}
	var head [512]byte
	n, e := f.Read(head[:])
	if e != nil && e != io.EOF {
		http.Error(w, "image unavailable", 500)
		return
	}
	mime := http.DetectContentType(head[:n])
	if !slices.Contains([]string{"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}, mime) {
		http.NotFound(w, r)
		return
	}
	if _, e := f.Seek(0, io.SeekStart); e != nil {
		http.Error(w, "image unavailable", 500)
		return
	}
	w.Header().Set("Content-Type", mime)
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Cache-Control", "private, max-age=300")
	http.ServeContent(w, r, path.Base(name), info.ModTime(), f)
}

func (a *app) dataImage(w http.ResponseWriter, r *http.Request)     { a.serveVisionFile(w, r, false) }
func (a *app) dataThumbnail(w http.ResponseWriter, r *http.Request) { a.serveVisionFile(w, r, true) }
