package main

import (
	"bytes"
	"context"
	"image"
	"image/color"
	"net/http"
	"testing"

	"golang.org/x/image/bmp"
	"golang.org/x/image/tiff"
)

func TestEVAL010BitmapAndTIFFByContent(t *testing.T) {
	img := image.NewRGBA(image.Rect(0, 0, 2, 3))
	img.Set(0, 0, color.RGBA{R: 240, A: 255})
	for _, item := range []struct {
		name   string
		encode func(*bytes.Buffer) error
	}{
		{"BMP", func(b *bytes.Buffer) error { return bmp.Encode(b, img) }},
		{"TIFF", func(b *bytes.Buffer) error { return tiff.Encode(b, img, nil) }},
	} {
		t.Run(item.name, func(t *testing.T) {
			var data bytes.Buffer
			if err := item.encode(&data); err != nil {
				t.Fatal(err)
			}
			handler := newEvalPredictHandler(recognizerFunc(func(_ context.Context, got image.Image) (string, error) {
				if got.Bounds().Dx() != 2 || got.Bounds().Dy() != 3 {
					t.Fatalf("bounds=%v", got.Bounds())
				}
				return "verified", nil
			}), 1)
			response := evalImageRequest(t, handler, "image", "misleading.jpg", data.Bytes(), nil)
			if response.Code != http.StatusOK {
				t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}
