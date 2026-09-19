package main

import (
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

const maxRequestBody = 64 << 10

type wine struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Winery      string `json:"winery"`
	Year        int    `json:"year"`
	Image       string `json:"image"`
	Description string `json:"description"`
}

type searchRequest struct {
	Scenario string  `json:"scenario"`
	Query    *string `json:"query"`
	PhotoID  *string `json:"photoId"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type searchResponse struct {
	Demo       bool      `json:"demo"`
	Candidates []wine    `json:"candidates"`
	SelectedID string    `json:"selectedId,omitempty"`
	Error      *apiError `json:"error,omitempty"`
}

//go:embed catalog.json
var embeddedCatalog []byte

var demoWines = mustLoadCatalog()

func mustLoadCatalog() []wine {
	var catalog []wine
	if err := json.Unmarshal(embeddedCatalog, &catalog); err != nil {
		panic("invalid embedded demo catalog: " + err.Error())
	}
	return catalog
}

func init() {
	_ = mime.AddExtensionType(".webmanifest", "application/manifest+json")
}

func main() {
	address := os.Getenv("ADDRESS")
	if address == "" {
		address = "127.0.0.1:8097"
	}
	log.Printf("demo API listening on %s", address)
	server := &http.Server{
		Addr:              address,
		Handler:           newHandler(os.Getenv("WEB_ROOT")),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    16 << 10,
	}
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func newHandler(webRoot string) http.Handler {
	store := configuredPhotoStore()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/docs", docsHandler)
	mux.HandleFunc("/api/docs/", docsHandler)
	mux.HandleFunc("/api/openapi.json", openAPIHandler)
	mux.HandleFunc("/api/schema/demo-search.schema.json", demoSearchSchemaHandler)
	mux.HandleFunc("/api/health", healthHandler)
	mux.HandleFunc("/api/catalog", catalogHandler)
	mux.HandleFunc("/api/photos", uploadHandler(store))
	mux.HandleFunc("/api/search", searchHandler(store))
	mux.HandleFunc("/api/", apiNotFoundHandler)
	if webRoot == "" {
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path == "/" {
				writeError(w, http.StatusNotFound, "web_root_not_configured", "WEB_ROOT is not configured")
				return
			}
			writeError(w, http.StatusNotFound, "not_found", "route not found")
		})
		return protectRequests(mux, time.Now)
	}
	mux.Handle("/", spaHandler(webRoot))
	return protectRequests(mux, time.Now)
}

func catalogHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	writeJSON(w, http.StatusOK, searchResponse{Demo: true, Candidates: demoWines})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true, "demo": true})
}

func searchHandler(store *photoStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		request, err := decodeSearchRequest(r)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid_request", err.Error())
			return
		}
		if request.PhotoID != nil {
			if !validPhotoID(*request.PhotoID) {
				writeError(w, http.StatusBadRequest, "invalid_photo_id", "photoId must be a stored receipt ID")
				return
			}
			if store == nil {
				writeError(w, http.StatusServiceUnavailable, "storage_unavailable", "photo storage is not configured")
				return
			}
			if !store.exists(*request.PhotoID) {
				writeError(w, http.StatusNotFound, "photo_not_found", "photo receipt was not found")
				return
			}
		}

		scenario := request.Scenario
		if scenario == "" {
			scenario = "exact"
		}
		switch scenario {
		case "exact":
			candidates := filterWines(request.Query)
			response := searchResponse{Demo: true, Candidates: candidates}
			if len(candidates) > 0 {
				response.SelectedID = candidates[0].ID
			}
			writeJSON(w, http.StatusOK, response)
		case "uncertain":
			writeJSON(w, http.StatusOK, searchResponse{Demo: true, Candidates: demoWines[:2]})
		case "none":
			writeJSON(w, http.StatusOK, searchResponse{Demo: true, Candidates: []wine{}})
		case "error":
			writeError(w, http.StatusServiceUnavailable, "demo_search_unavailable", "synthetic demo search failure")
		default:
			writeError(w, http.StatusBadRequest, "invalid_scenario", "scenario must be exact, uncertain, none, or error")
		}
	}
}

func decodeSearchRequest(r *http.Request) (searchRequest, error) {
	defer r.Body.Close()
	body, err := io.ReadAll(io.LimitReader(r.Body, maxRequestBody+1))
	if err != nil {
		return searchRequest{}, errors.New("request body is unreadable")
	}
	if len(body) > maxRequestBody {
		return searchRequest{}, errors.New("body must be a JSON object no larger than 64 KiB")
	}
	if !utf8.Valid(body) {
		return searchRequest{}, errors.New("body must be valid UTF-8")
	}
	trimmedBody := strings.TrimSpace(string(body))
	if len(trimmedBody) == 0 || trimmedBody[0] != '{' {
		return searchRequest{}, errors.New("body must be a JSON object")
	}
	decoder := json.NewDecoder(strings.NewReader(trimmedBody))
	decoder.DisallowUnknownFields()
	var request searchRequest
	if err := decoder.Decode(&request); err != nil {
		return searchRequest{}, errors.New("body must be a JSON object no larger than 64 KiB")
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return searchRequest{}, errors.New("body must contain one JSON object")
	}
	if request.Query != nil && strings.TrimSpace(*request.Query) == "" {
		return searchRequest{}, errors.New("query must not be empty when provided")
	}
	if request.Query != nil {
		if utf8.RuneCountInString(*request.Query) > 256 {
			return searchRequest{}, errors.New("query must be no longer than 256 characters")
		}
		for _, ch := range *request.Query {
			if unicode.IsControl(ch) {
				return searchRequest{}, errors.New("query must not contain control characters")
			}
		}
	}
	return request, nil
}

func filterWines(query *string) []wine {
	if query == nil {
		return demoWines
	}
	needle := strings.ToLower(strings.TrimSpace(*query))
	filtered := make([]wine, 0, len(demoWines))
	for _, candidate := range demoWines {
		if strings.Contains(strings.ToLower(candidate.Name), needle) || strings.Contains(strings.ToLower(candidate.Winery), needle) {
			filtered = append(filtered, candidate)
			continue
		}
		if strings.Contains(strconv.Itoa(candidate.Year), needle) {
			filtered = append(filtered, candidate)
		}
	}
	return filtered
}

func apiNotFoundHandler(w http.ResponseWriter, _ *http.Request) {
	writeError(w, http.StatusNotFound, "not_found", "API route not found")
}

func spaHandler(webRoot string) http.Handler {
	files := http.FileServer(http.Dir(webRoot))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			files.ServeHTTP(w, r)
			return
		}
		relativePath := strings.TrimPrefix(filepath.Clean(r.URL.Path), "/")
		if _, err := os.Stat(filepath.Join(webRoot, relativePath)); err == nil {
			files.ServeHTTP(w, r)
			return
		}
		http.ServeFile(w, r, filepath.Join(webRoot, "index.html"))
	})
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, searchResponse{Demo: true, Error: &apiError{Code: code, Message: message}})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
