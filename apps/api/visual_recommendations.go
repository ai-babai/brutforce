package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math"
	"os"
)

const maxRecommendationIndexBytes = 16 << 20

type visualNeighbor struct {
	ID    string  `json:"id"`
	Score float64 `json:"score"`
}

// Offline nearest neighbors use the same F8/F0 SO400M reference embeddings.
// These are visual alternatives, not recognition ranks or taste suggestions.
type recommendationIndex struct {
	CatalogVersion string                      `json:"catalogVersion"`
	ModelVersion   string                      `json:"modelVersion"`
	IndexVersion   string                      `json:"indexVersion"`
	Neighbors      map[string][]visualNeighbor `json:"neighbors"`
	configErr      error
}

func configuredRecommendationIndex() *recommendationIndex {
	path := os.Getenv("RECOMMENDATION_INDEX_FILE")
	if path == "" {
		return nil
	}
	index := &recommendationIndex{}
	file, err := os.Open(path)
	if err != nil {
		index.configErr = err
		return index
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxRecommendationIndexBytes+1))
	if err != nil || len(data) == 0 || len(data) > maxRecommendationIndexBytes {
		index.configErr = errors.New("visual similarity index is unavailable or too large")
		return index
	}
	wantedSHA, err := hex.DecodeString(os.Getenv("RECOMMENDATION_INDEX_SHA256"))
	actualSHA := sha256.Sum256(data)
	if err != nil || len(wantedSHA) != sha256.Size || !bytes.Equal(wantedSHA, actualSHA[:]) {
		index.configErr = errors.New("visual similarity index checksum mismatch")
		return index
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(index); err != nil {
		index.configErr = err
		return index
	}
	if decoder.Decode(&struct{}{}) != io.EOF || index.CatalogVersion == "" || index.ModelVersion == "" || index.IndexVersion == "" || len(index.CatalogVersion) > 128 || len(index.ModelVersion) > 128 || len(index.IndexVersion) > 128 || len(index.Neighbors) == 0 {
		index.configErr = errors.New("invalid visual similarity index metadata")
		return index
	}
	for source, neighbors := range index.Neighbors {
		if source == "" || len(neighbors) > 100 {
			index.configErr = errors.New("invalid visual similarity index source")
			return index
		}
		seen := map[string]bool{}
		last := 1.0
		for _, neighbor := range neighbors {
			if neighbor.ID == "" || neighbor.ID == source || seen[neighbor.ID] || math.IsNaN(neighbor.Score) || math.IsInf(neighbor.Score, 0) || neighbor.Score < 0 || neighbor.Score > last {
				index.configErr = errors.New("invalid visual similarity index neighbor")
				return index
			}
			seen[neighbor.ID] = true
			last = neighbor.Score
		}
	}
	return index
}

func visualRecommendations(info catalogInfo, known []wine, req recommendationsRequest, index *recommendationIndex) (searchResponse, int, string, string) {
	if index.configErr != nil {
		return searchResponse{}, 503, "recommendations_unavailable", "visual similarity index is unavailable for this catalog"
	}
	if index.CatalogVersion != info.Version {
		// The reviewed alpha release changes only display media. Its 2038 exact
		// IDs retain the same frozen SO400M vectors and nearest-neighbor order.
		if info.Version != "svoe-20260927-alpha-2035-v1" || index.CatalogVersion != "svoe-20260922-v2" || len(index.Neighbors) != len(known) {
			return searchResponse{}, 503, "recommendations_unavailable", "visual similarity index is unavailable for this catalog"
		}
		for _, item := range known {
			if _, ok := index.Neighbors[item.ID]; !ok {
				return searchResponse{}, 503, "recommendations_unavailable", "visual similarity index is unavailable for this catalog"
			}
		}
	}
	neighbors, ok := index.Neighbors[req.WineID]
	if !ok {
		return searchResponse{}, 503, "recommendations_unavailable", "source wine has no visual similarity index entry"
	}
	byID := make(map[string]wine, len(known))
	for _, item := range known {
		byID[item.ID] = item
	}
	limit := 5
	if req.Limit != nil {
		limit = *req.Limit
	}
	response := searchResponse{Demo: false, Candidates: []wine{}, CatalogVersion: info.Version, ModelVersion: index.ModelVersion, IndexVersion: index.IndexVersion}
	for _, neighbor := range neighbors[:min(limit, len(neighbors))] {
		item, exists := byID[neighbor.ID]
		if !exists {
			return searchResponse{}, 502, "recommendations_index_invalid", "visual similarity index references an absent display card"
		}
		response.Candidates = append(response.Candidates, item)
	}
	return response, 0, "", ""
}
