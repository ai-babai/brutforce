// Small container-only edge: local media, DB+vision readiness, existing Go API.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

var mediaPath = regexp.MustCompile(`^(400|800|original)/[0-9a-f]{64}\.webp$`)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--healthcheck" {
		client := &http.Client{Timeout: 4 * time.Second}
		resp, err := client.Get("http://127.0.0.1:8097/readyz")
		if err != nil || resp.StatusCode != http.StatusNoContent {
			os.Exit(1)
		}
		resp.Body.Close()
		return
	}
	upstream, _ := url.Parse("http://127.0.0.1:8098")
	proxy := httputil.NewSingleHostReverseProxy(upstream)
	mux := http.NewServeMux()
	mux.HandleFunc("/readyz", readiness)
	mux.HandleFunc("/media/catalog/", media)
	mux.Handle("/", proxy)
	server := &http.Server{Addr: ":8097", Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 30 * time.Second}
	if err := server.ListenAndServe(); err != nil {
		fmt.Fprintln(os.Stderr, "web proxy stopped:", err)
		os.Exit(1)
	}
}

func readiness(w http.ResponseWriter, r *http.Request) {
	client := &http.Client{Timeout: 2 * time.Second}
	for _, check := range []struct{ url, key, want string }{
		{"http://127.0.0.1:8098/v2/catalog?limit=1", "catalogVersion", os.Getenv("CATALOG_VERSION")},
		{os.Getenv("VISION_SERVICE_URL") + "/healthz", "model_version", "rtdetr-so400m-whole-only-v1-f8-text-confirmed-v1-onnx640"},
	} {
		if check.want == "" {
			http.Error(w, "configuration missing", http.StatusServiceUnavailable)
			return
		}
		resp, err := client.Get(check.url)
		if err != nil {
			http.Error(w, "dependency unavailable", http.StatusServiceUnavailable)
			return
		}
		var payload map[string]any
		err = json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&payload)
		resp.Body.Close()
		if err != nil || resp.StatusCode != 200 || payload[check.key] != check.want {
			http.Error(w, "dependency mismatch", http.StatusServiceUnavailable)
			return
		}
	}
	w.WriteHeader(http.StatusNoContent)
}

func media(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	rel := strings.TrimPrefix(r.URL.Path, "/media/catalog/")
	if !mediaPath.MatchString(rel) {
		http.NotFound(w, r)
		return
	}
	root := os.Getenv("CATALOG_MEDIA_DIR")
	base, err := filepath.EvalSymlinks(root)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	file, err := filepath.EvalSymlinks(filepath.Join(base, rel))
	if err != nil || !strings.HasPrefix(file, base+string(os.PathSeparator)) {
		http.NotFound(w, r)
		return
	}
	f, err := os.Open(file)
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "image/webp")
	w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
	http.ServeContent(w, r, rel, info.ModTime(), f)
}
