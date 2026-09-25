package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
)

const maxRequestBody = 64 << 10

// wine is kept as an alias while the older search and recommendation handlers
// are migrated. catalogmodel.Wine owns the JSON projection.
type wine = catalogmodel.Wine

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
	Demo           bool      `json:"demo"`
	Candidates     []wine    `json:"candidates"`
	SelectedID     string    `json:"selectedId,omitempty"`
	CatalogVersion string    `json:"catalogVersion,omitempty"`
	NextCursor     string    `json:"nextCursor,omitempty"`
	ModelVersion   string    `json:"modelVersion,omitempty"`
	FeedbackToken  string    `json:"feedbackToken,omitempty"`
	Error          *apiError `json:"error,omitempty"`
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
	catalog, closeCatalog, err := openConfiguredCatalog(context.Background())
	if err != nil {
		log.Fatal("catalog database is unavailable")
	}
	defer closeCatalog()
	address := os.Getenv("ADDRESS")
	if address == "" {
		address = "127.0.0.1:8097"
	}
	log.Printf("demo API listening on %s", address)
	server := &http.Server{
		Addr:              address,
		Handler:           newHandlerWithCatalogAndServices(os.Getenv("WEB_ROOT"), nil, catalog, configuredModelServices()),
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
	return newHandlerWithCatalog(webRoot, nil, embeddedCatalogStore{})
}

func newHandlerWithRecognizer(webRoot string, recognizer Recognizer) http.Handler {
	return newHandlerWithCatalog(webRoot, recognizer, embeddedCatalogStore{})
}

func newHandlerWithCatalog(webRoot string, recognizer Recognizer, catalog catalogReader) http.Handler {
	return newHandlerWithCatalogAndServices(webRoot, recognizer, catalog, modelServices{})
}

func newHandlerWithCatalogAndServices(webRoot string, recognizer Recognizer, catalog catalogReader, services modelServices) http.Handler {
	store := configuredPhotoStore()
	feedback := configuredFeedbackStore()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/docs", docsHandler)
	mux.HandleFunc("/api/docs/", docsHandler)
	mux.HandleFunc("/api/openapi.json", openAPIHandler)
	mux.HandleFunc("/api/schema/demo-search.schema.json", demoSearchSchemaHandler)
	mux.HandleFunc("/v1/health", healthHandler)
	mux.HandleFunc("/v2/catalog", catalogHandler(catalog))
	mux.HandleFunc("/v2/catalog/", catalogItemHandler(catalog))
	mux.HandleFunc("/v1/photos", uploadHandler(store))
	mux.HandleFunc("/v1/search", correlateServiceRequest(searchHandlerWithFeedback(store, feedback, catalog, services)))
	mux.HandleFunc("/v1/feedback", correlateServiceRequest(feedbackHandler(feedback, store, catalog)))
	mux.HandleFunc("/v1/recommendations", correlateServiceRequest(recommendationsHandler(catalog, services)))
	mux.HandleFunc("/v1/eval/predict", newEvalPredictHandler(recognizer, configuredEvalConcurrency()))
	mux.HandleFunc("/v1/", apiNotFoundHandler)
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

func catalogHandler(catalog catalogReader) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
			return
		}
		page, status, code, message := catalogPageForRequest(r, catalog)
		if status != 0 {
			writeError(w, status, code, message)
			return
		}
		if page.err != nil {
			writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			return
		}
		writeJSON(w, http.StatusOK, searchResponse{Demo: page.demo, Candidates: page.candidates, NextCursor: page.nextCursor, CatalogVersion: page.version})
	}
}

func catalogItemHandler(catalog catalogReader) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
			return
		}
		slug := strings.TrimPrefix(r.URL.Path, "/v2/catalog/")
		if slug == "" || strings.Contains(slug, "/") {
			writeError(w, http.StatusNotFound, "not_found", "catalog item was not found")
			return
		}
		item, canonicalID, info, err := catalogLookup(r.Context(), catalog, slug)
		if err != nil {
			if errors.Is(err, errCatalogNotFound) {
				writeError(w, http.StatusNotFound, "not_found", "catalog item was not found")
			} else {
				writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			}
			return
		}
		writeJSON(w, http.StatusOK, struct {
			Demo           bool   `json:"demo"`
			Candidate      wine   `json:"candidate"`
			CanonicalID    string `json:"canonicalId"`
			CatalogVersion string `json:"catalogVersion"`
		}{info.Demo, item, canonicalID, info.Version})
	}
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true, "demo": true})
}

func searchHandler(store *photoStore, catalog catalogReader, services modelServices) http.HandlerFunc {
	return searchHandlerWithFeedback(store, nil, catalog, services)
}

func searchHandlerWithFeedback(store *photoStore, feedback *feedbackStore, catalog catalogReader, services modelServices) http.HandlerFunc {
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
		info, err := catalogInfoFor(r.Context(), catalog)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			return
		}
		if !info.Demo && services.search == nil {
			writeError(w, http.StatusServiceUnavailable, "recognition_unavailable", "reference recognition is unavailable for the imported catalog")
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
		if services.search != nil {
			if request.Query == nil && request.PhotoID == nil {
				writeError(w, http.StatusBadRequest, "invalid_request", "query or photoId is required when search service is configured")
				return
			}
			response, status, code, message := configuredSearch(r, store, catalog, request, services.search)
			if status != 0 {
				writeError(w, status, code, message)
				return
			}
			if !attachFeedbackSession(w, r, store, feedback, request, &response) {
				return
			}
			writeJSON(w, http.StatusOK, response)
			return
		}

		scenario := request.Scenario
		if scenario == "" {
			scenario = "exact"
		}
		switch scenario {
		case "exact":
			candidates, err := demoSearchPage(r.Context(), catalog, request.Query, 5)
			if err != nil {
				writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
				return
			}
			response := searchResponse{Demo: true, Candidates: candidates, CatalogVersion: info.Version}
			if len(candidates) > 0 {
				response.SelectedID = candidates[0].ID
			}
			if !attachFeedbackSession(w, r, store, feedback, request, &response) {
				return
			}
			writeJSON(w, http.StatusOK, response)
		case "uncertain":
			candidates, err := demoSearchPage(r.Context(), catalog, nil, 2)
			if err != nil {
				writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
				return
			}
			response := searchResponse{Demo: true, Candidates: candidates, CatalogVersion: info.Version}
			if !attachFeedbackSession(w, r, store, feedback, request, &response) {
				return
			}
			writeJSON(w, http.StatusOK, response)
		case "none":
			response := searchResponse{Demo: true, Candidates: []wine{}, CatalogVersion: info.Version}
			if !attachFeedbackSession(w, r, store, feedback, request, &response) {
				return
			}
			writeJSON(w, http.StatusOK, response)
		case "error":
			writeError(w, http.StatusServiceUnavailable, "demo_search_unavailable", "synthetic demo search failure")
		default:
			writeError(w, http.StatusBadRequest, "invalid_scenario", "scenario must be exact, uncertain, none, or error")
		}
	}
}

// The synthetic photo route mirrors the model contract's small candidate set.
// Its curated demo order is distinct from the browsable catalog's ID order.
func demoSearchPage(ctx context.Context, catalog catalogReader, query *string, limit int) ([]wine, error) {
	candidates, err := catalog.Search(ctx, query)
	if err != nil {
		return nil, err
	}
	if len(candidates) > limit {
		candidates = candidates[:limit]
	}
	return candidates, nil
}

func attachFeedbackSession(w http.ResponseWriter, r *http.Request, photos *photoStore, feedback *feedbackStore, request searchRequest, response *searchResponse) bool {
	if request.PhotoID == nil || feedback == nil {
		return true
	}
	token, err := feedback.createSession(photos, *request.PhotoID, r.Header.Get("X-Request-ID"), *response)
	if err != nil {
		writeError(w, http.StatusServiceUnavailable, "feedback_unavailable", "cannot prepare photo feedback")
		return false
	}
	response.FeedbackToken = token
	return true
}

type recommendationsRequest struct {
	WineID string `json:"wineId"`
	Limit  *int   `json:"limit,omitempty"`
}

func recommendationsHandler(catalog catalogReader, services modelServices) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		if services.recommendations == nil {
			writeError(w, http.StatusServiceUnavailable, "recommendations_unavailable", "recommendation service is not configured")
			return
		}
		info, err := catalogInfoFor(r.Context(), catalog)
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			return
		}
		if !info.Demo {
			writeError(w, http.StatusServiceUnavailable, "recommendations_unavailable", "reference recommendations are unavailable for the imported catalog")
			return
		}
		var req recommendationsRequest
		if err := decodeBoundedJSON(r, maxRequestBody, &req); err != nil || strings.TrimSpace(req.WineID) == "" || utf8.RuneCountInString(req.WineID) > 128 || !validLimit(req.Limit) {
			writeError(w, http.StatusBadRequest, "invalid_request", "wineId and an optional limit from 1 to 10 are required")
			return
		}
		known, err := catalog.List(r.Context())
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable")
			return
		}
		found := false
		for _, candidate := range known {
			if candidate.ID == req.WineID {
				found = true
				break
			}
		}
		if !found {
			writeError(w, http.StatusNotFound, "wine_not_found", "wineId is not in the demo catalog")
			return
		}
		response, status, code, message := configuredRecommendations(r, catalog, req, services.recommendations)
		if status != 0 {
			writeError(w, status, code, message)
			return
		}
		writeJSON(w, http.StatusOK, response)
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
