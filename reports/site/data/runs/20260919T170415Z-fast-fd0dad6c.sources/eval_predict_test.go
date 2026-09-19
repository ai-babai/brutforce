package main

import (
	"bytes"
	"context"
	"encoding/json"
	"image"
	"image/color"
	"image/png"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

type recognizerFunc func(context.Context, image.Image) (string, error)

func (f recognizerFunc) Recognize(ctx context.Context, img image.Image) (string, error) {
	return f(ctx, img)
}

func TestEVAL001PredictReturnsRecognizerSlugWithoutNormalization(t *testing.T) {
	const slug = "slug_from_recognizer_2026"
	h := newEvalPredictHandler(recognizerFunc(func(_ context.Context, img image.Image) (string, error) {
		if got := img.Bounds().Size(); got.X != 2 || got.Y != 3 {
			t.Fatalf("decoded size=%v", got)
		}
		return slug, nil
	}), 1)

	w := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
	if w.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
	var response struct {
		Slug string `json:"slug"`
	}
	if err := json.NewDecoder(w.Body).Decode(&response); err != nil || response.Slug != slug {
		t.Fatalf("response=%+v err=%v", response, err)
	}
}

func TestEVAL002PredictDecodesWebPByContentNotFilename(t *testing.T) {
	data, err := os.ReadFile("/Users/skif/ml-data/brutforce/materials/2026-09-19-organizers/dataset/eval/queries/019c68d0.jpg")
	if err != nil {
		t.Fatal(err)
	}
	h := newEvalPredictHandler(recognizerFunc(func(_ context.Context, img image.Image) (string, error) {
		if got := img.Bounds().Size(); got.X != 3024 || got.Y != 4032 {
			t.Fatalf("decoded WebP dimensions=%v", got)
		}
		return "webp-content-was-decoded", nil
	}), 1)
	w := evalImageRequest(t, h, "image", "misleading.jpg", data, nil)
	if w.Code != http.StatusOK || !strings.Contains(w.Body.String(), "webp-content-was-decoded") {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestEVAL003PredictRejectsMalformedOrAmbiguousInput(t *testing.T) {
	h := newEvalPredictHandler(recognizerFunc(func(context.Context, image.Image) (string, error) { return "unused", nil }), 1)
	for _, item := range []struct {
		name  string
		field string
		data  []byte
		extra func(*multipart.Writer)
	}{
		{"missing image", "other", smallPNG(t), nil},
		{"invalid bytes", "image", []byte("not-an-image"), nil},
		{"additional field", "image", smallPNG(t), func(mw *multipart.Writer) { _ = mw.WriteField("note", "no") }},
		{"two images", "image", smallPNG(t), func(mw *multipart.Writer) {
			p, _ := mw.CreateFormFile("image", "second.png")
			_, _ = p.Write(smallPNG(t))
		}},
	} {
		t.Run(item.name, func(t *testing.T) {
			w := evalImageRequest(t, h, item.field, "label.jpg", item.data, item.extra)
			if w.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
			}
		})
	}
}

func TestEVAL007PredictBoundsAndFullDecode(t *testing.T) {
	h := newEvalPredictHandler(recognizerFunc(func(context.Context, image.Image) (string, error) { return "unused", nil }), 1)
	for _, item := range []struct {
		name string
		data []byte
	}{
		{"truncated PNG", pngBytes(t)[:33]},
		{"pixel limit", pngIHDR(5_001, 5_001)},
		{"dimension limit", pngIHDR(12_001, 1)},
		{"byte limit", bytes.Repeat([]byte("x"), maxEvalImageBytes+1)},
	} {
		t.Run(item.name, func(t *testing.T) {
			w := evalImageRequest(t, h, "image", "label.png", item.data, nil)
			if w.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
			}
		})
	}
}

func TestEVAL004PredictMethodAndUnknownAPIRoute(t *testing.T) {
	h := newHandlerWithRecognizer("", recognizerFunc(func(context.Context, image.Image) (string, error) { return "unused", nil }))
	for _, item := range []struct {
		method, path string
		want         int
	}{
		{http.MethodGet, "/v1/eval/predict", http.StatusMethodNotAllowed},
		{http.MethodGet, "/v1/eval/unknown", http.StatusNotFound},
	} {
		w := request(t, h, item.method, item.path, "")
		if w.Code != item.want {
			t.Fatalf("%s %s status=%d want=%d", item.method, item.path, w.Code, item.want)
		}
	}
}

func TestEVAL005PredictWithoutRecognizerIsHonest503(t *testing.T) {
	w := evalImageRequest(t, newHandler(""), "image", "label.png", smallPNG(t), nil)
	if w.Code != http.StatusServiceUnavailable || !strings.Contains(w.Body.String(), `"recognition_unavailable"`) || strings.Contains(w.Body.String(), `"slug"`) {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestEVAL006PredictPassesCancellationToRecognizer(t *testing.T) {
	started := make(chan struct{}, 1)
	cancelled := make(chan struct{}, 1)
	h := newEvalPredictHandler(recognizerFunc(func(ctx context.Context, _ image.Image) (string, error) {
		deadline, ok := ctx.Deadline()
		until := time.Until(deadline)
		if !ok || until <= 0 || until >= 10*time.Second {
			t.Fatalf("contest deadline=%v present=%t", deadline, ok)
		}
		started <- struct{}{}
		<-ctx.Done()
		cancelled <- struct{}{}
		return "", ctx.Err()
	}), 1)
	req := evalMultipartRequest(t, "image", "label.png", smallPNG(t), nil)
	ctx, cancel := context.WithCancel(req.Context())
	defer cancel()
	req = req.WithContext(ctx)
	w := httptest.NewRecorder()
	done := make(chan struct{})
	go func() { h.ServeHTTP(w, req); close(done) }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("recognizer did not start")
	}
	cancel()
	select {
	case <-cancelled:
	case <-time.After(time.Second):
		t.Fatal("recognizer did not receive request cancellation")
	}
	<-done
	if w.Code != http.StatusRequestTimeout {
		t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
	}
}

func TestEVAL008PredictIsStatelessAndNotDemoRateLimited(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("UPLOAD_DIR", dir)
	h := newHandlerWithRecognizer("", recognizerFunc(func(context.Context, image.Image) (string, error) { return "slug", nil }))
	for i := 0; i < 12; i++ {
		w := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
		if w.Code != http.StatusOK {
			t.Fatalf("sequential request %d status=%d body=%s", i+1, w.Code, w.Body.String())
		}
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatalf("contest predict persisted files: %v", entries)
	}
}

func TestEVAL009PredictHasSeparateConcurrencyCap(t *testing.T) {
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	h := newEvalPredictHandler(recognizerFunc(func(context.Context, image.Image) (string, error) {
		started <- struct{}{}
		<-release
		return "slug", nil
	}), 1)
	first := make(chan *httptest.ResponseRecorder, 1)
	go func() { first <- evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil) }()
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("first recognition did not start")
	}
	busy := evalImageRequest(t, h, "image", "label.png", smallPNG(t), nil)
	if busy.Code != http.StatusTooManyRequests || busy.Header().Get("Retry-After") != "1" {
		t.Fatalf("busy status=%d retry-after=%q", busy.Code, busy.Header().Get("Retry-After"))
	}
	close(release)
	if result := <-first; result.Code != http.StatusOK {
		t.Fatalf("first status=%d body=%s", result.Code, result.Body.String())
	}
}

func smallPNG(t *testing.T) []byte {
	t.Helper()
	var buffer bytes.Buffer
	img := image.NewRGBA(image.Rect(0, 0, 2, 3))
	img.Set(0, 0, color.RGBA{R: 0xff, A: 0xff})
	if err := png.Encode(&buffer, img); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func evalImageRequest(t *testing.T, h http.Handler, field, filename string, data []byte, extra func(*multipart.Writer)) *httptest.ResponseRecorder {
	t.Helper()
	req := evalMultipartRequest(t, field, filename, data, extra)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)
	return w
}

func evalMultipartRequest(t *testing.T, field, filename string, data []byte, extra func(*multipart.Writer)) *http.Request {
	t.Helper()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	part, err := writer.CreateFormFile(field, filename)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write(data); err != nil {
		t.Fatal(err)
	}
	if extra != nil {
		extra(writer)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/eval/predict", &body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	return req
}
