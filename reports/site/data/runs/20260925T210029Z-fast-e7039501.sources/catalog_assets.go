package main

import (
	"context"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func catalogAssetsHandler(store catalogReader, root string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET or HEAD")
			return
		}
		if root == "" {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/catalog-assets/"), "/")
		if len(parts) < 2 || !safeCatalogVersion(parts[0]) {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		version, relative := parts[0], strings.Join(parts[1:], "/")
		known, err := hasCatalogVersion(r.Context(), store, version)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			return
		}
		if !known || !safeAssetPath(relative) || !strings.HasPrefix(relative, "images/") {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		base := filepath.Join(root, version)
		file := filepath.Join(base, filepath.FromSlash(relative))
		if !within(base, file) || hasSymlink(base, file) {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		stat, err := os.Stat(file)
		if err != nil || stat.IsDir() {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		if filepath.Ext(file) != ".webp" {
			writeError(w, http.StatusNotFound, "not_found", "catalog asset was not found")
			return
		}
		w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		http.ServeFile(w, r, file)
	})
}
func hasCatalogVersion(ctx context.Context, store catalogReader, version string) (bool, error) {
	if x, ok := store.(catalogVersionRegistry); ok {
		return x.HasCatalogVersion(ctx, version)
	}
	info, err := catalogInfoFor(ctx, store)
	return err == nil && info.Version == version, err
}
func safeCatalogVersion(value string) bool {
	if value == "" || len(value) > 128 {
		return false
	}
	for _, c := range value {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '.' || c == '-' || c == '_') {
			return false
		}
	}
	return true
}
func safeAssetPath(path string) bool {
	return path != "" && !strings.Contains(path, "\\") && !strings.HasPrefix(path, "/") && !strings.Contains(path, "..")
}
func within(base, file string) bool {
	rel, err := filepath.Rel(base, file)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}
func hasSymlink(base, file string) bool {
	baseInfo, err := os.Lstat(base)
	if err != nil || baseInfo.Mode()&os.ModeSymlink != 0 {
		return true
	}
	rel, err := filepath.Rel(base, file)
	if err != nil {
		return true
	}
	current := base
	for _, part := range strings.Split(rel, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return true
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return true
		}
	}
	return false
}
