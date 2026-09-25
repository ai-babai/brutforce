package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"image"
	"image/png"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
	"unicode/utf8"
)

const maxVisionResponse = 1 << 20

var (
	errVisionInvalid      = errors.New("invalid vision response")
	errVisionNoMatch      = errors.New("vision found no target")
	errVisionInsufficient = errors.New("vision found insufficient evidence")
)

type visionClient struct {
	baseURL, catalogVersion, indexVersion string
	client                                *http.Client
	configErr                             error
	validSlugs                            map[string]struct{}
}

type visionResult struct {
	Slug           string   `json:"slug"`
	Action         string   `json:"action"`
	RankedSlugs    []string `json:"ranked_slugs"`
	CatalogVersion string   `json:"catalog_version"`
	IndexVersion   string   `json:"index_version"`
	ModelVersion   string   `json:"model_version"`
}

func configuredVisionClient() *visionClient {
	raw := os.Getenv("VISION_SERVICE_URL")
	if raw == "" {
		return nil
	}
	c := &visionClient{catalogVersion: os.Getenv("VISION_CATALOG_VERSION"), indexVersion: os.Getenv("VISION_INDEX_VERSION"), client: noRedirectHTTPClient()}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		c.configErr = errors.New("invalid vision URL")
		return c
	}
	c.baseURL = strings.TrimRight(raw, "/")
	c.validSlugs, c.configErr = loadVisionSlugs(os.Getenv("VISION_SLUGS_FILE"), os.Getenv("VISION_SLUGS_SHA256"), c.catalogVersion)
	return c
}

func loadVisionSlugs(path, wantedSHA, wantedVersion string) (map[string]struct{}, error) {
	if path == "" || wantedSHA == "" || wantedVersion == "" {
		return nil, errors.New("vision slug allowlist is not configured")
	}
	data, err := os.ReadFile(path)
	if err != nil || len(data) == 0 || len(data) > maxVisionResponse {
		return nil, errors.New("vision slug allowlist is unavailable")
	}
	checksum, err := hex.DecodeString(wantedSHA)
	actualSHA := sha256.Sum256(data)
	if err != nil || len(checksum) != sha256.Size || !bytes.Equal(checksum, actualSHA[:]) {
		return nil, errors.New("vision slug allowlist checksum mismatch")
	}
	var catalog struct {
		Version string   `json:"catalog_version"`
		Slugs   []string `json:"slugs"`
	}
	if json.Unmarshal(data, &catalog) != nil || catalog.Version != wantedVersion || len(catalog.Slugs) == 0 || len(catalog.Slugs) > 10000 {
		return nil, errors.New("vision slug allowlist version or shape is invalid")
	}
	known := make(map[string]struct{}, len(catalog.Slugs))
	for _, slug := range catalog.Slugs {
		if slug == "" || len(slug) > 512 {
			return nil, errVisionInvalid
		}
		if _, duplicate := known[slug]; duplicate {
			return nil, errVisionInvalid
		}
		known[slug] = struct{}{}
	}
	return known, nil
}

func (c *visionClient) predict(ctx context.Context, data []byte) (visionResult, error) {
	if c.configErr != nil {
		return visionResult{}, c.configErr
	}
	ctx, cancel := context.WithTimeout(ctx, 8500*time.Millisecond)
	defer cancel()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile("image", "photo.bin")
	if err == nil {
		_, err = part.Write(data)
	}
	if err == nil {
		err = writer.Close()
	}
	if err != nil {
		return visionResult{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/eval/predict?track=service", &body)
	if err != nil {
		return visionResult{}, err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Accept", "application/json")
	response, err := c.client.Do(req)
	if err != nil {
		return visionResult{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return visionResult{}, modelHTTPStatus(response.StatusCode)
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return visionResult{}, errVisionInvalid
	}
	data, err = io.ReadAll(io.LimitReader(response.Body, maxVisionResponse+1))
	if err != nil || len(data) > maxVisionResponse || !utf8.Valid(data) {
		return visionResult{}, errVisionInvalid
	}
	var result visionResult
	var fields map[string]json.RawMessage
	if json.Unmarshal(data, &fields) != nil || fields == nil || json.Unmarshal(data, &result) != nil || result.RankedSlugs == nil {
		return visionResult{}, errVisionInvalid
	}
	if result.CatalogVersion == "" || result.IndexVersion == "" || result.ModelVersion == "" || len(result.CatalogVersion) > 256 || len(result.IndexVersion) > 256 || len(result.ModelVersion) > 256 || len(result.RankedSlugs) > 20 {
		return visionResult{}, errVisionInvalid
	}
	if (c.catalogVersion != "" && result.CatalogVersion != c.catalogVersion) || (c.indexVersion != "" && result.IndexVersion != c.indexVersion) {
		return visionResult{}, errVisionInvalid
	}
	if len(result.RankedSlugs) == 0 {
		if result.Slug != "" || (result.Action != "no_match" && result.Action != "insufficient_information") {
			return visionResult{}, errVisionInvalid
		}
		return result, nil
	}
	if result.Slug != result.RankedSlugs[0] || result.Action != "" {
		return visionResult{}, errVisionInvalid
	}
	seen := make(map[string]bool, len(result.RankedSlugs))
	for _, slug := range result.RankedSlugs {
		if slug == "" || len(slug) > 512 || seen[slug] {
			return visionResult{}, errVisionInvalid
		}
		if c.validSlugs != nil {
			if _, ok := c.validSlugs[slug]; !ok {
				return visionResult{}, errVisionInvalid
			}
		}
		seen[slug] = true
	}
	return result, nil
}

type visionRecognizer struct {
	client *visionClient
}

// Recognize satisfies the original injection contract; normal HTTP requests
// use RecognizeEncoded so that the exact validated input bytes reach inference.
func (v *visionRecognizer) Recognize(ctx context.Context, img image.Image) (string, error) {
	var data bytes.Buffer
	if err := png.Encode(&data, img); err != nil {
		return "", err
	}
	return v.RecognizeEncoded(ctx, data.Bytes())
}

func (v *visionRecognizer) RecognizeEncoded(ctx context.Context, data []byte) (string, error) {
	result, err := v.client.predict(ctx, data)
	if err != nil {
		return "", err
	}
	if result.Action == "no_match" {
		return "", errVisionNoMatch
	}
	if result.Action == "insufficient_information" {
		return "", errVisionInsufficient
	}
	return result.Slug, nil
}

func configuredVisionSearch(r *http.Request, store *photoStore, catalog catalogReader, photoID string, client *visionClient) (searchResponse, int, string, string) {
	if !validPhotoID(photoID) {
		return searchResponse{}, 400, "invalid_photo_id", "photoId must be a stored receipt ID"
	}
	if store == nil {
		return searchResponse{}, 503, "storage_unavailable", "photo storage is not configured"
	}
	data, err := store.readOriginal(photoID)
	if err != nil {
		return searchResponse{}, 404, "photo_not_found", "photo receipt was not found"
	}
	result, err := client.predict(r.Context(), data)
	if err != nil {
		response, status, code, message := upstreamFailure("recognition", err)
		_ = response
		return searchResponse{}, status, code, message
	}
	info, err := catalogInfoFor(r.Context(), catalog)
	if err != nil || info.Demo {
		return searchResponse{}, 503, "catalog_unavailable", "catalog is temporarily unavailable"
	}
	response := searchResponse{Demo: false, Candidates: []wine{}, CatalogVersion: info.Version, RecognitionCatalogVersion: result.CatalogVersion, ModelVersion: result.ModelVersion}
	if len(result.RankedSlugs) == 0 {
		response.Action = result.Action
		return response, 0, "", ""
	}
	known, err := catalog.List(r.Context())
	if err != nil {
		return searchResponse{}, 503, "catalog_unavailable", "catalog is temporarily unavailable"
	}
	bySlug := make(map[string]wine, len(known))
	for _, item := range known {
		bySlug[item.Slug] = item
	}
	response.RecognizedSlug = result.Slug
	if _, ok := bySlug[result.Slug]; !ok {
		response.Action = "outside_display_catalog"
		return response, 0, "", ""
	}
	for _, slug := range result.RankedSlugs[:min(5, len(result.RankedSlugs))] {
		item, ok := bySlug[slug]
		if !ok {
			response.Action = "partial_display_catalog"
			continue
		}
		response.Candidates = append(response.Candidates, item)
	}
	// Candidate rank is evidence for inspection, not calibrated confidence.
	// Selection remains explicit in the product UI until its UX rule is settled.
	return response, 0, "", ""
}
