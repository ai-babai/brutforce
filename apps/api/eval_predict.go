package main

import (
	"bytes"
	"context"
	"errors"
	"golang.org/x/image/draw"
	_ "golang.org/x/image/webp"
	"image"
	"image/jpeg"
	"io"
	"mime"
	"net/http"
	"os"
	"strconv"
	"time"
)

const (
	maxEvalImageBytes       = 10 << 20
	maxEvalMultipartBytes   = maxEvalImageBytes + (1 << 20)
	maxEvalImagePixels      = 25_000_000
	maxEvalSourcePixels     = 50_000_000
	maxEvalImageDimension   = 12_000
	maxEvalResizedSide      = 4_000
	defaultEvalConcurrency  = 4
	evalRecognitionDeadline = 9 * time.Second
)

// Recognizer is the only dependency of the contest HTTP boundary. It receives
// a decoded, bounded image and must return the exact catalog slug it selected.
// The executable wires a versioned HTTP adapter when VISION_SERVICE_URL is set.
type Recognizer interface {
	Recognize(context.Context, image.Image) (string, error)
}

// EncodedRecognizer receives the validated original bytes, avoiding a second
// image encode before forwarding to a remote inference process.
type EncodedRecognizer interface {
	RecognizeEncoded(context.Context, []byte) (string, error)
}

// RankedEncodedRecognizer exposes the existing upstream order for optional
// evaluation requests without starting another inference.
type RankedEncodedRecognizer interface {
	RecognizeRankedEncoded(context.Context, []byte) ([]string, error)
}

type evalErrorResponse struct {
	Error apiError `json:"error"`
}

func newEvalPredictHandler(recognizer Recognizer, maxConcurrent int) http.HandlerFunc {
	if maxConcurrent < 1 {
		maxConcurrent = 1
	}
	slots := make(chan struct{}, maxConcurrent)
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeEvalError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST")
			return
		}
		topKValues, supplied := r.URL.Query()["top_k"]
		if supplied && (len(topKValues) != 1 || topKValues[0] != "5") {
			writeEvalError(w, http.StatusBadRequest, "invalid_request", "top_k must be 5 when supplied")
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), evalRecognitionDeadline)
		defer cancel()
		mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
		if err != nil || mediaType != "multipart/form-data" {
			writeEvalError(w, http.StatusBadRequest, "invalid_request", "content type must be multipart/form-data")
			return
		}
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			w.Header().Set("Retry-After", "1")
			writeEvalError(w, http.StatusTooManyRequests, "recognition_busy", "too many recognition requests are in progress")
			return
		}

		img, encoded, err := decodeEvalImage(w, r)
		if err != nil {
			writeEvalError(w, http.StatusBadRequest, "invalid_image", err.Error())
			return
		}
		if err := ctx.Err(); err != nil {
			writeEvalContextError(w, err)
			return
		}
		if recognizer == nil {
			writeEvalError(w, http.StatusServiceUnavailable, "recognition_unavailable", "recognition is not configured")
			return
		}
		var slug string
		var ranked []string
		if supplied {
			raw, ok := recognizer.(RankedEncodedRecognizer)
			if !ok {
				writeEvalError(w, http.StatusServiceUnavailable, "recognition_unavailable", "ranked recognition is not configured")
				return
			}
			ranked, err = raw.RecognizeRankedEncoded(ctx, encoded)
			if len(ranked) > 0 {
				slug = ranked[0]
			}
		} else if raw, ok := recognizer.(EncodedRecognizer); ok {
			slug, err = raw.RecognizeEncoded(ctx, encoded)
		} else {
			slug, err = recognizer.Recognize(ctx, img)
		}
		if err != nil {
			if ctx.Err() != nil {
				writeEvalContextError(w, ctx.Err())
			} else if errors.Is(err, context.DeadlineExceeded) {
				writeEvalContextError(w, err)
			} else if errors.Is(err, context.Canceled) {
				writeEvalContextError(w, err)
			} else if errors.Is(err, errVisionNoMatch) {
				writeEvalAction(w, "no_match", supplied)
			} else if errors.Is(err, errVisionInsufficient) {
				writeEvalAction(w, "insufficient_information", supplied)
			} else if errors.Is(err, errVisionInvalid) || errors.Is(err, errCatalogNotFound) {
				writeEvalError(w, http.StatusBadGateway, "recognition_invalid_result", "recognition returned an invalid catalog result")
			} else {
				writeEvalError(w, http.StatusServiceUnavailable, "recognition_failed", "recognition failed")
			}
			return
		}
		if err := ctx.Err(); err != nil {
			writeEvalContextError(w, err)
			return
		}
		if supplied {
			if len(ranked) > 20 || len(ranked) == 0 {
				writeEvalError(w, http.StatusBadGateway, "recognition_invalid_result", "recognition returned an invalid ranking")
				return
			}
			seen := make(map[string]bool, len(ranked))
			for _, candidate := range ranked {
				if candidate == "" || seen[candidate] {
					writeEvalError(w, http.StatusBadGateway, "recognition_invalid_result", "recognition returned an invalid ranking")
					return
				}
				seen[candidate] = true
			}
			if len(ranked) > 5 {
				ranked = ranked[:5]
			}
			writeJSON(w, http.StatusOK, struct {
				Slug        string   `json:"slug"`
				RankedSlugs []string `json:"ranked_slugs"`
			}{Slug: slug, RankedSlugs: ranked})
			return
		}
		if slug == "" {
			writeEvalError(w, http.StatusServiceUnavailable, "recognition_invalid_result", "recognition returned an empty slug")
			return
		}
		writeJSON(w, http.StatusOK, struct {
			Slug string `json:"slug"`
		}{Slug: slug})
	}
}

func writeEvalAction(w http.ResponseWriter, action string, ranked bool) {
	if ranked {
		writeJSON(w, http.StatusOK, struct {
			Action      string   `json:"action"`
			RankedSlugs []string `json:"ranked_slugs"`
		}{Action: action, RankedSlugs: []string{}})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"action": action})
}

func writeEvalContextError(w http.ResponseWriter, err error) {
	if errors.Is(err, context.DeadlineExceeded) {
		writeEvalError(w, http.StatusGatewayTimeout, "recognition_timeout", "recognition did not finish before the deadline")
		return
	}
	writeEvalError(w, http.StatusRequestTimeout, "request_cancelled", "request was cancelled")
}

func configuredEvalConcurrency() int {
	raw := os.Getenv("EVAL_MAX_CONCURRENT")
	if raw == "" {
		return defaultEvalConcurrency
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 {
		return defaultEvalConcurrency
	}
	return value
}

func decodeEvalImage(w http.ResponseWriter, r *http.Request) (image.Image, []byte, error) {
	r.Body = http.MaxBytesReader(w, r.Body, maxEvalMultipartBytes)
	reader, err := r.MultipartReader()
	if err != nil {
		return nil, nil, errors.New("multipart form is invalid")
	}
	var data []byte
	imageParts := 0
	for {
		part, err := reader.NextPart()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, nil, errors.New("multipart form is invalid or too large")
		}
		if part.FormName() != "image" || part.FileName() == "" {
			return nil, nil, errors.New("multipart form must contain exactly one image file field")
		}
		imageParts++
		if imageParts > 1 {
			return nil, nil, errors.New("multipart field image must be supplied once")
		}
		data, err = io.ReadAll(io.LimitReader(part, maxEvalImageBytes+1))
		if err != nil || len(data) > maxEvalImageBytes {
			return nil, nil, errors.New("image must be no larger than 10 MiB")
		}
	}
	if data == nil {
		return nil, nil, errors.New("multipart field image is required")
	}
	config, format, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil || config.Width <= 0 || config.Height <= 0 || config.Width > maxEvalImageDimension || config.Height > maxEvalImageDimension || int64(config.Width) > maxEvalSourcePixels/int64(config.Height) {
		return nil, nil, errors.New("image must be a decodable JPEG, PNG, GIF, WebP, BMP, or TIFF image within the allowed pixel limit")
	}
	decoded, decodedFormat, err := image.Decode(bytes.NewReader(data))
	if err != nil || decodedFormat != format || decoded.Bounds().Dx() != config.Width || decoded.Bounds().Dy() != config.Height {
		return nil, nil, errors.New("image must be fully decodable")
	}
	if int64(config.Width) > maxEvalImagePixels/int64(config.Height) {
		// Originals above the serving limit are bounded before forwarding. Small
		// images still use their exact validated bytes as before.
		longest := config.Width
		if config.Height > longest {
			longest = config.Height
		}
		width := config.Width * maxEvalResizedSide / longest
		height := config.Height * maxEvalResizedSide / longest
		resized := image.NewRGBA(image.Rect(0, 0, width, height))
		draw.ApproxBiLinear.Scale(resized, resized.Bounds(), decoded, decoded.Bounds(), draw.Over, nil)
		var normalized bytes.Buffer
		if err := jpeg.Encode(&normalized, resized, &jpeg.Options{Quality: 88}); err != nil {
			return nil, nil, errors.New("image normalization failed")
		}
		if normalized.Len() > maxEvalImageBytes {
			return nil, nil, errors.New("normalized image exceeds the serving byte limit")
		}
		return resized, normalized.Bytes(), nil
	}
	return decoded, data, nil
}

func writeEvalError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, evalErrorResponse{Error: apiError{Code: code, Message: message}})
}
