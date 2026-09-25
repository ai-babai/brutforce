package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unicode"
	"unicode/utf8"
)

const maxFeedbackCommentRunes = 2000

type feedbackCandidate struct {
	ID   string `json:"id"`
	Slug string `json:"slug,omitempty"`
	Rank int    `json:"rank"`
}

type feedbackSession struct {
	SchemaVersion  int                 `json:"schemaVersion"`
	Token          string              `json:"token"`
	CreatedAt      string              `json:"createdAt"`
	PhotoID        string              `json:"photoId"`
	PhotoSHA256    string              `json:"photoSha256"`
	RequestID      string              `json:"requestId"`
	CatalogVersion string              `json:"catalogVersion"`
	ModelVersion   string              `json:"modelVersion,omitempty"`
	Demo           bool                `json:"demo"`
	SelectedID     string              `json:"selectedId,omitempty"`
	Outcome        string              `json:"outcome"`
	Candidates     []feedbackCandidate `json:"candidates"`
}

type feedbackRequest struct {
	FeedbackToken   string `json:"feedbackToken"`
	IdempotencyKey  string `json:"idempotencyKey"`
	Decision        string `json:"decision"`
	DisplayedWineID string `json:"displayedWineId"`
	CorrectWineID   string `json:"correctWineId,omitempty"`
	Comment         string `json:"comment,omitempty"`
}

type feedbackRecord struct {
	SchemaVersion        int                 `json:"schemaVersion"`
	FeedbackID           string              `json:"feedbackId"`
	CreatedAt            string              `json:"createdAt"`
	IdempotencyKey       string              `json:"idempotencyKey"`
	PayloadSHA256        string              `json:"payloadSha256"`
	Source               string              `json:"source"`
	CampaignID           string              `json:"campaignId"`
	ReviewStatus         string              `json:"reviewStatus"`
	TrainingEligible     bool                `json:"trainingEligible"`
	OriginRightsStatus   string              `json:"originRightsStatus"`
	HeldOutStatus        string              `json:"heldOutStatus"`
	PhotoID              string              `json:"photoId"`
	PhotoSHA256          string              `json:"photoSha256"`
	SearchResultID       string              `json:"searchResultId"`
	RequestID            string              `json:"requestId"`
	CatalogVersion       string              `json:"catalogVersion"`
	ModelVersion         string              `json:"modelVersion,omitempty"`
	Demo                 bool                `json:"demo"`
	OriginalOutcome      string              `json:"originalOutcome"`
	OriginalSelectedID   string              `json:"originalSelectedId,omitempty"`
	OriginalCandidates   []feedbackCandidate `json:"originalCandidates"`
	DisplayedWineID      string              `json:"displayedWineId"`
	DisplayOrigin        string              `json:"displayOrigin"`
	Decision             string              `json:"decision"`
	TargetCanonicalID    string              `json:"targetCanonicalId"`
	TargetSlug           string              `json:"targetSlug"`
	TargetCatalogVersion string              `json:"targetCatalogVersion"`
	Comment              string              `json:"comment,omitempty"`
}

type feedbackReceipt struct {
	FeedbackID   string `json:"feedbackId"`
	CreatedAt    string `json:"createdAt"`
	ReviewStatus string `json:"reviewStatus"`
	Duplicate    bool   `json:"duplicate"`
}

type feedbackStore struct {
	dir        string
	campaignID string
	mu         sync.Mutex
}

func configuredFeedbackStore() *feedbackStore {
	dir := strings.TrimSpace(os.Getenv("FEEDBACK_DIR"))
	if dir == "" {
		return nil
	}
	store, err := openFeedbackStore(dir)
	if err != nil {
		return nil
	}
	store.campaignID = strings.TrimSpace(os.Getenv("FEEDBACK_CAMPAIGN_ID"))
	if store.campaignID == "" {
		store.campaignID = "test-default"
	}
	return store
}

func openFeedbackStore(dir string) (*feedbackStore, error) {
	for _, path := range []string{dir, filepath.Join(dir, "sessions"), filepath.Join(dir, "records")} {
		if err := os.MkdirAll(path, 0o700); err != nil {
			return nil, err
		}
		if err := os.Chmod(path, 0o700); err != nil {
			return nil, err
		}
	}
	return &feedbackStore{dir: dir}, nil
}

func (store *feedbackStore) createSession(photoStore *photoStore, photoID, requestID string, response searchResponse) (string, error) {
	if store == nil || photoStore == nil {
		return "", errors.New("feedback storage unavailable")
	}
	data, err := photoStore.readOriginal(photoID)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(data)
	candidates := make([]feedbackCandidate, 0, len(response.Candidates))
	for index, candidate := range response.Candidates {
		candidates = append(candidates, feedbackCandidate{ID: candidate.ID, Slug: candidate.Slug, Rank: index + 1})
	}
	outcome := "no_match"
	if len(candidates) > 0 {
		outcome = "matched"
	}
	for attempts := 0; attempts < 8; attempts++ {
		token, err := randomPhotoID()
		if err != nil {
			return "", err
		}
		session := feedbackSession{
			SchemaVersion: 1, Token: token, CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
			PhotoID: photoID, PhotoSHA256: hex.EncodeToString(digest[:]), RequestID: requestID,
			CatalogVersion: response.CatalogVersion, ModelVersion: response.ModelVersion, Demo: response.Demo,
			SelectedID: response.SelectedID, Outcome: outcome, Candidates: candidates,
		}
		payload, err := json.Marshal(session)
		if err != nil {
			return "", err
		}
		payload = append(payload, '\n')
		err = writeAtomicFile(filepath.Join(store.dir, "sessions", token+".json"), payload)
		if err == nil {
			return token, nil
		}
		if !os.IsExist(err) {
			return "", err
		}
	}
	return "", errors.New("cannot allocate feedback session")
}

func (store *feedbackStore) readSession(token string) (feedbackSession, error) {
	if store == nil || !validPhotoID(token) {
		return feedbackSession{}, os.ErrNotExist
	}
	data, err := os.ReadFile(filepath.Join(store.dir, "sessions", token+".json"))
	if err != nil {
		return feedbackSession{}, err
	}
	var session feedbackSession
	if json.Unmarshal(data, &session) != nil || session.SchemaVersion != 1 || session.Token != token || !validPhotoID(session.PhotoID) {
		return feedbackSession{}, errors.New("invalid feedback session")
	}
	return session, nil
}

func feedbackHandler(store *feedbackStore, photos *photoStore, catalog catalogReader) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		if store == nil || photos == nil {
			writeError(w, http.StatusServiceUnavailable, "feedback_unavailable", "feedback storage is not configured")
			return
		}
		var request feedbackRequest
		if err := decodeBoundedJSON(r, maxRequestBody, &request); err != nil {
			writeError(w, http.StatusBadRequest, "invalid_request", "feedback body is invalid")
			return
		}
		request.Comment = strings.TrimSpace(request.Comment)
		if !validPhotoID(request.FeedbackToken) || !validPhotoID(request.IdempotencyKey) ||
			(request.Decision != "confirm" && request.Decision != "correct") ||
			utf8.RuneCountInString(request.Comment) > maxFeedbackCommentRunes || hasUnsafeControls(request.Comment) {
			writeError(w, http.StatusBadRequest, "invalid_feedback", "feedback fields are invalid")
			return
		}
		if request.Decision == "confirm" && (request.CorrectWineID != "" || strings.TrimSpace(request.DisplayedWineID) == "") {
			writeError(w, http.StatusBadRequest, "invalid_feedback", "confirmed feedback must not include correctWineId")
			return
		}
		if request.Decision == "correct" && (strings.TrimSpace(request.CorrectWineID) == "" || (request.DisplayedWineID != "" && request.CorrectWineID == request.DisplayedWineID)) {
			writeError(w, http.StatusBadRequest, "invalid_feedback", "corrected feedback requires a different catalog wine")
			return
		}
		normalized, _ := json.Marshal(request)
		payloadDigest := sha256.Sum256(normalized)
		payloadSHA := hex.EncodeToString(payloadDigest[:])
		if receipt, found, err := store.existingReceipt(request.IdempotencyKey, payloadSHA); err != nil {
			if errors.Is(err, errFeedbackConflict) {
				writeError(w, http.StatusConflict, "idempotency_conflict", "idempotency key was already used for different feedback")
				return
			}
			writeError(w, http.StatusServiceUnavailable, "feedback_unavailable", "feedback could not be read")
			return
		} else if found {
			writeJSON(w, http.StatusOK, receipt)
			return
		}
		session, err := store.readSession(request.FeedbackToken)
		if err != nil || !photos.exists(session.PhotoID) {
			writeError(w, http.StatusNotFound, "feedback_session_not_found", "feedback session was not found")
			return
		}
		displayedKnown := session.Outcome == "no_match" && request.Decision == "correct" && request.DisplayedWineID == ""
		for _, candidate := range session.Candidates {
			if candidate.ID == request.DisplayedWineID {
				displayedKnown = true
				break
			}
		}
		if !displayedKnown {
			writeError(w, http.StatusConflict, "feedback_snapshot_mismatch", "displayed wine is not part of this search result")
			return
		}
		targetID := request.DisplayedWineID
		if request.Decision == "correct" {
			targetID = request.CorrectWineID
		}
		target, info, err := catalogLookupByID(r.Context(), catalog, targetID)
		if err != nil {
			status := http.StatusServiceUnavailable
			code := "catalog_unavailable"
			if errors.Is(err, errCatalogNotFound) {
				status, code = http.StatusNotFound, "wine_not_found"
			}
			writeError(w, status, code, "target wine is unavailable")
			return
		}
		if session.CatalogVersion != "" && info.Version != session.CatalogVersion {
			writeError(w, http.StatusConflict, "catalog_version_mismatch", "catalog changed after the search")
			return
		}
		feedbackID, err := randomPhotoID()
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "feedback_unavailable", "cannot initialize feedback")
			return
		}
		createdAt := time.Now().UTC().Format(time.RFC3339Nano)
		displayOrigin := "model_result"
		if request.DisplayedWineID == "" {
			displayOrigin = "model_no_match"
		} else if session.SelectedID == "" || session.SelectedID != request.DisplayedWineID {
			displayOrigin = "manual_candidate_selection"
		}
		targetSlug := target.Slug
		if targetSlug == "" {
			targetSlug = target.ID
		}
		record := feedbackRecord{
			SchemaVersion: 1, FeedbackID: feedbackID, CreatedAt: createdAt, IdempotencyKey: request.IdempotencyKey,
			PayloadSHA256: payloadSHA, Source: "test_photo_feedback", CampaignID: store.campaignID, ReviewStatus: "pending_review", TrainingEligible: false,
			OriginRightsStatus: "unverified", HeldOutStatus: "unverified", PhotoID: session.PhotoID,
			PhotoSHA256: session.PhotoSHA256, SearchResultID: session.Token, RequestID: session.RequestID,
			CatalogVersion: session.CatalogVersion, ModelVersion: session.ModelVersion, Demo: session.Demo,
			OriginalOutcome: session.Outcome, OriginalSelectedID: session.SelectedID, OriginalCandidates: session.Candidates,
			DisplayedWineID: request.DisplayedWineID, DisplayOrigin: displayOrigin, Decision: request.Decision,
			TargetCanonicalID: target.ID, TargetSlug: targetSlug, TargetCatalogVersion: info.Version, Comment: request.Comment,
		}
		receipt, status, err := store.saveRecord(record)
		if errors.Is(err, errFeedbackConflict) {
			writeError(w, http.StatusConflict, "idempotency_conflict", "idempotency key was already used for different feedback")
			return
		}
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "feedback_unavailable", "feedback could not be saved")
			return
		}
		writeJSON(w, status, receipt)
	}
}

var errFeedbackConflict = errors.New("feedback idempotency conflict")

func (store *feedbackStore) existingReceipt(key, payloadSHA string) (feedbackReceipt, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	data, err := os.ReadFile(filepath.Join(store.dir, "records", key+".json"))
	if errors.Is(err, os.ErrNotExist) {
		return feedbackReceipt{}, false, nil
	}
	if err != nil {
		return feedbackReceipt{}, false, err
	}
	var prior feedbackRecord
	if json.Unmarshal(data, &prior) != nil {
		return feedbackReceipt{}, false, errors.New("invalid stored feedback")
	}
	if prior.PayloadSHA256 != payloadSHA {
		return feedbackReceipt{}, false, errFeedbackConflict
	}
	return feedbackReceipt{FeedbackID: prior.FeedbackID, CreatedAt: prior.CreatedAt, ReviewStatus: prior.ReviewStatus, Duplicate: true}, true, nil
}

func (store *feedbackStore) saveRecord(record feedbackRecord) (feedbackReceipt, int, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	path := filepath.Join(store.dir, "records", record.IdempotencyKey+".json")
	if existing, err := os.ReadFile(path); err == nil {
		var prior feedbackRecord
		if json.Unmarshal(existing, &prior) != nil {
			return feedbackReceipt{}, 0, errors.New("invalid stored feedback")
		}
		if prior.PayloadSHA256 != record.PayloadSHA256 {
			return feedbackReceipt{}, 0, errFeedbackConflict
		}
		return feedbackReceipt{FeedbackID: prior.FeedbackID, CreatedAt: prior.CreatedAt, ReviewStatus: prior.ReviewStatus, Duplicate: true}, http.StatusOK, nil
	} else if !os.IsNotExist(err) {
		return feedbackReceipt{}, 0, err
	}
	payload, err := json.Marshal(record)
	if err != nil {
		return feedbackReceipt{}, 0, err
	}
	payload = append(payload, '\n')
	if err := writeAtomicFile(path, payload); err != nil {
		return feedbackReceipt{}, 0, err
	}
	return feedbackReceipt{FeedbackID: record.FeedbackID, CreatedAt: record.CreatedAt, ReviewStatus: record.ReviewStatus}, http.StatusCreated, nil
}

func hasUnsafeControls(value string) bool {
	for _, character := range value {
		if unicode.IsControl(character) && character != '\n' && character != '\r' && character != '\t' {
			return true
		}
	}
	return false
}
