package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
	"unicode/utf8"

	"brutforce-behavior-demo/apps/api/internal/referenceengine"
)

const (
	defaultCatalogVersion = "demo-v1"
	maxModelResponse      = 64 << 10
)

type modelCandidate = referenceengine.Candidate
type modelResponse = referenceengine.Response

type modelServices struct {
	search          *modelClient
	recommendations *modelClient
}

type modelClient struct {
	baseURL        string
	catalogVersion string
	client         *http.Client
	configErr      error
}

func configuredModelServices() modelServices {
	version := os.Getenv("CATALOG_VERSION")
	if version == "" {
		version = defaultCatalogVersion
	}
	newClient := func(raw string) *modelClient {
		if raw == "" {
			return nil
		}
		if parsed, err := url.ParseRequestURI(raw); err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
			return &modelClient{configErr: errors.New("invalid service URL")}
		}
		return &modelClient{baseURL: strings.TrimRight(raw, "/"), catalogVersion: version, client: noRedirectHTTPClient()}
	}
	return modelServices{search: newClient(os.Getenv("SEARCH_SERVICE_URL")), recommendations: newClient(os.Getenv("RECOMMENDATION_SERVICE_URL"))}
}

func noRedirectHTTPClient() *http.Client {
	return &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
}

func (c *modelClient) request(ctx context.Context, path, contentType string, body io.Reader, timeout time.Duration, requestID string) (modelResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, body)
	if err != nil {
		return modelResponse{}, err
	}
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("Accept", "application/json")
	if safeRequestID(requestID) {
		req.Header.Set("X-Request-ID", requestID)
	}
	response, err := c.client.Do(req)
	if err != nil {
		return modelResponse{}, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return modelResponse{}, modelHTTPStatus(response.StatusCode)
	}
	media, _, parseErr := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if parseErr != nil || media != "application/json" {
		return modelResponse{}, errModelResponse
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, maxModelResponse+1))
	if err != nil {
		return modelResponse{}, err
	}
	if len(data) > maxModelResponse {
		return modelResponse{}, errModelResponse
	}
	var result modelResponse
	result, err = referenceengine.DecodeResponse(data)
	if err != nil {
		return modelResponse{}, errModelResponse
	}
	return result, nil
}

func configuredSearch(r *http.Request, store *photoStore, catalog catalogReader, input searchRequest, client *modelClient) (searchResponse, int, string, string) {
	if client.configErr != nil {
		return searchResponse{}, http.StatusServiceUnavailable, "search_unavailable", "search service is misconfigured"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 9*time.Second)
	defer cancel()
	limit := 5
	var result modelResponse
	var err error
	if input.Query == nil && input.PhotoID != nil {
		data, readErr := store.readOriginal(*input.PhotoID)
		if readErr != nil {
			return searchResponse{}, http.StatusBadGateway, "search_upstream_invalid", "stored photo is unavailable for search"
		}
		var body bytes.Buffer
		writer := multipart.NewWriter(&body)
		part, partErr := writer.CreateFormFile("image", "photo.bin")
		if partErr == nil {
			_, partErr = part.Write(data)
		}
		if partErr == nil {
			partErr = writer.WriteField("catalogVersion", client.catalogVersion)
		}
		if partErr == nil {
			partErr = writer.WriteField("limit", "5")
		}
		if partErr == nil {
			partErr = writer.Close()
		}
		if partErr != nil {
			return searchResponse{}, http.StatusBadGateway, "search_upstream_invalid", "cannot prepare image search request"
		}
		result, err = client.request(ctx, "/v1/search/image", writer.FormDataContentType(), &body, 8*time.Second, r.Header.Get("X-Request-ID"))
	} else {
		query := ""
		if input.Query != nil {
			query = *input.Query
		}
		payload, _ := json.Marshal(struct {
			Query          string `json:"query"`
			CatalogVersion string `json:"catalogVersion"`
			Limit          int    `json:"limit"`
		}{query, client.catalogVersion, limit})
		result, err = client.request(ctx, "/v1/search/text", "application/json", bytes.NewReader(payload), time.Second, r.Header.Get("X-Request-ID"))
	}
	if err != nil {
		return upstreamFailure("search", err)
	}
	return enrichModelResponse(ctx, catalog, result, client.catalogVersion, "", true, limit)
}

func configuredRecommendations(r *http.Request, catalog catalogReader, input recommendationsRequest, client *modelClient) (searchResponse, int, string, string) {
	if client.configErr != nil {
		return searchResponse{}, http.StatusServiceUnavailable, "recommendations_unavailable", "recommendation service is misconfigured"
	}
	ctx, cancel := context.WithTimeout(r.Context(), time.Second)
	defer cancel()
	limit := 5
	if input.Limit != nil {
		limit = *input.Limit
	}
	payload, _ := json.Marshal(struct {
		WineID         string `json:"wineId"`
		CatalogVersion string `json:"catalogVersion"`
		Limit          int    `json:"limit"`
	}{input.WineID, client.catalogVersion, limit})
	result, err := client.request(ctx, "/v1/recommendations", "application/json", bytes.NewReader(payload), time.Second, r.Header.Get("X-Request-ID"))
	if err != nil {
		return upstreamFailure("recommendations", err)
	}
	return enrichModelResponse(ctx, catalog, result, client.catalogVersion, input.WineID, false, limit)
}

func enrichModelResponse(ctx context.Context, catalog catalogReader, result modelResponse, wantedVersion, sourceID string, allowSelected bool, maxCandidates int) (searchResponse, int, string, string) {
	if result.CatalogVersion != wantedVersion || result.ModelVersion == "" || len(result.ModelVersion) > 128 || result.Candidates == nil || len(result.Candidates) > maxCandidates {
		return searchResponse{}, http.StatusBadGateway, "model_response_invalid", "model response does not match the configured catalog"
	}
	known, err := catalog.List(ctx)
	if err != nil {
		return searchResponse{}, http.StatusServiceUnavailable, "catalog_unavailable", "catalog is temporarily unavailable"
	}
	byID := make(map[string]wine, len(known))
	for _, item := range known {
		byID[item.ID] = item
	}
	seen := make(map[string]bool, len(result.Candidates))
	response := searchResponse{Demo: true, Candidates: make([]wine, 0, len(result.Candidates)), CatalogVersion: result.CatalogVersion, ModelVersion: result.ModelVersion}
	last := 1.0
	for i, candidate := range result.Candidates {
		item, ok := byID[candidate.ID]
		if !ok || seen[candidate.ID] || candidate.ID == sourceID || candidate.Score < 0 || candidate.Score > 1 || (i > 0 && candidate.Score > last) {
			return searchResponse{}, http.StatusBadGateway, "model_response_invalid", "model response contains invalid candidates"
		}
		seen[candidate.ID] = true
		last = candidate.Score
		response.Candidates = append(response.Candidates, item)
	}
	if allowSelected && result.SelectedID != "" {
		if !seen[result.SelectedID] {
			return searchResponse{}, http.StatusBadGateway, "model_response_invalid", "selected result is not a candidate"
		}
		response.SelectedID = result.SelectedID
	} else if !allowSelected && result.SelectedID != "" {
		return searchResponse{}, http.StatusBadGateway, "model_response_invalid", "recommendations must not select a result"
	}
	return response, 0, "", ""
}

var errModelResponse = errors.New("invalid model response")

type modelHTTPStatus int

func (s modelHTTPStatus) Error() string { return fmt.Sprintf("upstream status %d", int(s)) }

func upstreamFailure(kind string, err error) (searchResponse, int, string, string) {
	var status modelHTTPStatus
	if errors.Is(err, context.DeadlineExceeded) || (errors.As(err, &status) && status == 504) {
		return searchResponse{}, 504, kind + "_timeout", kind + " service timed out"
	}
	if errors.Is(err, context.Canceled) {
		return searchResponse{}, 408, kind + "_canceled", "request was canceled"
	}
	if errors.Is(err, errModelResponse) || (errors.As(err, &status) && status != 503 && status != 429) {
		return searchResponse{}, 502, kind + "_upstream_invalid", kind + " service returned an invalid response"
	}
	return searchResponse{}, 503, kind + "_unavailable", kind + " service is unavailable"
}

// Correlation and the total processing budget start before catalog/provider work.
func correlateServiceRequest(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if !safeRequestID(id) {
			var err error
			id, err = randomPhotoID()
			if err != nil {
				writeError(w, 500, "request_id_unavailable", "cannot initialize request")
				return
			}
		}
		ctx, cancel := context.WithTimeout(r.Context(), 9*time.Second)
		defer cancel()
		r = r.Clone(ctx)
		r.Header.Set("X-Request-ID", id)
		w.Header().Set("X-Request-ID", id)
		next(w, r)
	}
}

func validLimit(limit *int) bool { return limit == nil || (*limit >= 1 && *limit <= 10) }

func safeRequestID(value string) bool {
	if value == "" || len(value) > 64 {
		return false
	}
	for _, c := range value {
		if !(c == '-' || c >= '0' && c <= '9' || c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z') {
			return false
		}
	}
	return true
}

func decodeBoundedJSON(r *http.Request, max int, target any) error {
	defer r.Body.Close()
	data, err := io.ReadAll(io.LimitReader(r.Body, int64(max)+1))
	if err != nil || len(data) > max {
		return errors.New("body is unreadable")
	}
	if !utf8.Valid(data) {
		return errors.New("invalid UTF-8")
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(data, &fields) != nil || fields == nil {
		return errors.New("JSON object required")
	}
	for _, raw := range fields {
		if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
			return errors.New("null fields are not allowed")
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return errors.New("multiple values")
	}
	return nil
}
