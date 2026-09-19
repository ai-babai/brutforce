package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	maxPhotoBytes         = 10 << 20
	maxMultipartBytes     = maxPhotoBytes + (1 << 20)
	defaultUploadMaxBytes = 200 << 20
	defaultMaxPhotoPixels = 25_000_000
)

var (
	errStorageFull  = errors.New("photo storage limit reached")
	errInvalidPhoto = errors.New("photo must be a JPEG, PNG, or GIF image within the allowed pixel limit")
)

type photoReceipt struct {
	ID        string `json:"id"`
	CreatedAt string `json:"createdAt"`
	Bytes     int64  `json:"bytes"`
	MIME      string `json:"mime"`
	Width     int    `json:"width"`
	Height    int    `json:"height"`
}

type photoStore struct {
	dir       string
	maxBytes  int64
	maxPixels int64
	usedBytes int64
	mu        sync.Mutex
}

func configuredPhotoStore() *photoStore {
	dir := os.Getenv("UPLOAD_DIR")
	if dir == "" {
		return nil
	}
	maxBytes, err := positiveEnvInt64("UPLOAD_MAX_BYTES", defaultUploadMaxBytes)
	if err != nil {
		return nil
	}
	maxPixels, err := positiveEnvInt64("UPLOAD_MAX_PIXELS", defaultMaxPhotoPixels)
	if err != nil {
		return nil
	}
	store, err := openPhotoStore(dir, maxBytes, maxPixels)
	if err != nil {
		return nil
	}
	return store
}

func positiveEnvInt64(name string, fallback int64) (int64, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value <= 0 {
		return 0, errors.New("invalid storage limit")
	}
	return value, nil
}

func openPhotoStore(dir string, maxBytes, maxPixels int64) (*photoStore, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	if err := os.Chmod(dir, 0o700); err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var used int64
	for _, entry := range entries {
		if entry.Type().IsRegular() {
			info, err := entry.Info()
			if err != nil {
				return nil, err
			}
			used += info.Size()
		}
	}
	return &photoStore{dir: dir, maxBytes: maxBytes, maxPixels: maxPixels, usedBytes: used}, nil
}

func uploadHandler(store *photoStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		if store == nil {
			writeError(w, http.StatusServiceUnavailable, "storage_unavailable", "photo storage is not configured")
			return
		}
		if _, _, err := mime.ParseMediaType(r.Header.Get("Content-Type")); err != nil || !strings.HasPrefix(r.Header.Get("Content-Type"), "multipart/form-data") {
			writeError(w, http.StatusBadRequest, "invalid_upload", "content type must be multipart/form-data")
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, maxMultipartBytes)
		reader, err := r.MultipartReader()
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid_upload", "multipart form is invalid")
			return
		}
		var data []byte
		photoParts := 0
		for {
			part, err := reader.NextPart()
			if errors.Is(err, io.EOF) {
				break
			}
			if err != nil {
				writeError(w, http.StatusBadRequest, "invalid_upload", "multipart form is invalid or too large")
				return
			}
			if part.FormName() != "photo" {
				continue
			}
			photoParts++
			if photoParts > 1 {
				writeError(w, http.StatusBadRequest, "invalid_upload", "multipart field photo must be supplied once")
				return
			}
			data, err = io.ReadAll(io.LimitReader(part, maxPhotoBytes+1))
			if err != nil || len(data) > maxPhotoBytes {
				writeError(w, http.StatusBadRequest, "invalid_upload", "photo must be no larger than 10 MiB")
				return
			}
		}
		if data == nil {
			writeError(w, http.StatusBadRequest, "invalid_upload", "multipart field photo is required")
			return
		}
		config, imageFormat, err := image.DecodeConfig(bytes.NewReader(data))
		if err != nil || config.Width <= 0 || config.Height <= 0 || int64(config.Width) > store.maxPixels/int64(config.Height) {
			writeError(w, http.StatusBadRequest, "invalid_photo", errInvalidPhoto.Error())
			return
		}
		mimeType, ok := map[string]string{"jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}[imageFormat]
		if !ok {
			writeError(w, http.StatusBadRequest, "invalid_photo", errInvalidPhoto.Error())
			return
		}
		receipt, err := store.save(data, mimeType, config)
		if errors.Is(err, errStorageFull) {
			writeError(w, http.StatusServiceUnavailable, "storage_full", "photo storage limit reached")
			return
		}
		if err != nil {
			writeError(w, http.StatusServiceUnavailable, "storage_unavailable", "photo storage is unavailable")
			return
		}
		writeJSON(w, http.StatusCreated, receipt)
	}
}

func (store *photoStore) save(data []byte, mimeType string, config image.Config) (photoReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	for {
		id, err := randomPhotoID()
		if err != nil {
			return photoReceipt{}, err
		}
		receipt := photoReceipt{ID: id, CreatedAt: time.Now().UTC().Format(time.RFC3339Nano), Bytes: int64(len(data)), MIME: mimeType, Width: config.Width, Height: config.Height}
		metadata, err := json.Marshal(receipt)
		if err != nil {
			return photoReceipt{}, err
		}
		metadata = append(metadata, '\n')
		addedBytes := int64(len(data) + len(metadata))
		if store.usedBytes+addedBytes > store.maxBytes {
			return photoReceipt{}, errStorageFull
		}
		originalPath := store.originalPath(id)
		metadataPath := store.metadataPath(id)
		if _, err := os.Stat(originalPath); err == nil {
			continue
		}
		if _, err := os.Stat(metadataPath); err == nil {
			continue
		}
		if err := writeAtomicFile(originalPath, data); err != nil {
			return photoReceipt{}, err
		}
		if err := writeAtomicFile(metadataPath, metadata); err != nil {
			_ = os.Remove(originalPath)
			return photoReceipt{}, err
		}
		store.usedBytes += addedBytes
		return receipt, nil
	}
}

func (store *photoStore) exists(id string) bool {
	store.mu.Lock()
	defer store.mu.Unlock()
	metadata, err := os.ReadFile(store.metadataPath(id))
	if err != nil {
		return false
	}
	var receipt photoReceipt
	if json.Unmarshal(metadata, &receipt) != nil || receipt.ID != id {
		return false
	}
	info, err := os.Stat(store.originalPath(id))
	return err == nil && info.Mode().IsRegular() && info.Size() == receipt.Bytes
}

func (store *photoStore) originalPath(id string) string { return filepath.Join(store.dir, id+".bin") }
func (store *photoStore) metadataPath(id string) string { return filepath.Join(store.dir, id+".json") }

func randomPhotoID() (string, error) {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

func validPhotoID(id string) bool {
	if len(id) != 32 {
		return false
	}
	for _, character := range id {
		if !((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f')) {
			return false
		}
	}
	return true
}

func writeAtomicFile(path string, data []byte) error {
	temporaryPath := path + ".tmp"
	file, err := os.OpenFile(temporaryPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	if _, err := file.Write(data); err != nil {
		file.Close()
		_ = os.Remove(temporaryPath)
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		_ = os.Remove(temporaryPath)
		return err
	}
	if err := file.Close(); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	return os.Rename(temporaryPath, path)
}
