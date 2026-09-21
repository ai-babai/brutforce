package main

import (
	"bytes"
	"encoding/binary"
	"hash/crc32"
	"image"
	"image/color"
	"image/gif"
	"image/jpeg"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"os"
	"sync"
	"testing"
)

func TestSEC001RejectsDisguisedNonImages(t *testing.T) {
	for _, item := range []struct {
		name string
		data []byte
	}{
		{"zip named png", []byte("PK\x03\x04not-an-image")},
		{"svg named jpg", []byte("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>")},
	} {
		t.Run(item.name, func(t *testing.T) {
			store := securityPhotoStore(t)
			recorder := uploadRequest(t, uploadHandler(store), item.data)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			assertNoStoredFiles(t, store)
		})
	}
	t.Run("zip with spoofed image MIME", func(t *testing.T) {
		store := securityPhotoStore(t)
		recorder := multipartUploadWithPhotoMIME(t, uploadHandler(store), []byte("PK\x03\x04not-an-image"), "image/png")
		if recorder.Code != http.StatusBadRequest {
			t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
		}
		assertNoStoredFiles(t, store)
	})
}

func TestSEC002RejectsTruncatedImageAfterDecodeConfig(t *testing.T) {
	data := pngBytes(t)[:33] // PNG signature and a complete IHDR, but no pixel data.
	if _, _, err := image.DecodeConfig(bytes.NewReader(data)); err != nil {
		t.Fatalf("fixture must pass DecodeConfig: %v", err)
	}
	store := securityPhotoStore(t)
	recorder := uploadRequest(t, uploadHandler(store), data)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	assertNoStoredFiles(t, store)

	for _, item := range []struct {
		name string
		data []byte
	}{
		{"jpeg", jpegBytes(t)},
		{"gif first frame", gifBytes(t)},
	} {
		t.Run("accepts valid "+item.name, func(t *testing.T) {
			store := securityPhotoStore(t)
			recorder := uploadRequest(t, uploadHandler(store), item.data)
			if recorder.Code != http.StatusCreated {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
		})
	}
}

func TestSEC003RejectsTinyOversizedImageConfig(t *testing.T) {
	for _, item := range []struct {
		name          string
		width, height uint32
	}{
		{"pixel limit", 5_001, 5_001}, // 25,010,001 pixels in only 33 bytes.
		{"single dimension limit", 12_001, 1},
	} {
		t.Run(item.name, func(t *testing.T) {
			data := pngIHDR(item.width, item.height)
			config, _, err := image.DecodeConfig(bytes.NewReader(data))
			if err != nil || config.Width != int(item.width) || config.Height != int(item.height) {
				t.Fatalf("fixture config=%+v err=%v", config, err)
			}
			store := securityPhotoStore(t)
			recorder := uploadRequest(t, uploadHandler(store), data)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			assertNoStoredFiles(t, store)
		})
	}
}

func TestSEC004RejectsInvalidMultipartAndOversizeFile(t *testing.T) {
	tooLarge := bytes.Repeat([]byte("x"), maxPhotoBytes+1)
	for _, item := range []struct {
		name  string
		parts func(t *testing.T, writer *multipart.Writer)
	}{
		{
			name: "additional field",
			parts: func(t *testing.T, writer *multipart.Writer) {
				t.Helper()
				field, err := writer.CreateFormField("note")
				if err != nil {
					t.Fatal(err)
				}
				_, _ = field.Write([]byte("not allowed"))
				writePhotoPart(t, writer, pngBytes(t))
			},
		},
		{
			name: "two photo files",
			parts: func(t *testing.T, writer *multipart.Writer) {
				writePhotoPart(t, writer, pngBytes(t))
				writePhotoPart(t, writer, pngBytes(t))
			},
		},
		{
			name: "photo without filename",
			parts: func(t *testing.T, writer *multipart.Writer) {
				field, err := writer.CreateFormField("photo")
				if err != nil {
					t.Fatal(err)
				}
				_, _ = field.Write(pngBytes(t))
			},
		},
		{
			name: "file exceeds byte cap",
			parts: func(t *testing.T, writer *multipart.Writer) {
				writePhotoPart(t, writer, tooLarge)
			},
		},
	} {
		t.Run(item.name, func(t *testing.T) {
			store := securityPhotoStore(t)
			recorder := multipartUpload(t, uploadHandler(store), item.parts)
			if recorder.Code != http.StatusBadRequest {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			assertNoStoredFiles(t, store)
		})
	}
}

func TestSEC005LimitsConcurrentUploads(t *testing.T) {
	store := securityPhotoStore(t)
	handler := uploadHandlerWithConcurrency(store, 2)
	body := multipartBody(t, func(t *testing.T, writer *multipart.Writer) { writePhotoPart(t, writer, pngBytes(t)) })
	release := make(chan struct{})
	first := newGatedBody(body.data, release)
	second := newGatedBody(body.data, release)
	firstResult := make(chan *httptest.ResponseRecorder, 1)
	secondResult := make(chan *httptest.ResponseRecorder, 1)
	go func() { firstResult <- serveUpload(handler, body.contentType, first) }()
	<-first.started
	go func() { secondResult <- serveUpload(handler, body.contentType, second) }()
	<-second.started

	third := &countingReadCloser{ReadCloser: io.NopCloser(bytes.NewReader(body.data))}
	thirdResult := serveUpload(handler, body.contentType, third)
	if thirdResult.Code != http.StatusTooManyRequests || thirdResult.Header().Get("Retry-After") != "1" || third.reads != 0 {
		t.Fatalf("third status=%d retry-after=%q reads=%d", thirdResult.Code, thirdResult.Header().Get("Retry-After"), third.reads)
	}

	close(release)
	if result := <-firstResult; result.Code != http.StatusCreated {
		t.Fatalf("first status=%d body=%s", result.Code, result.Body.String())
	}
	if result := <-secondResult; result.Code != http.StatusCreated {
		t.Fatalf("second status=%d body=%s", result.Code, result.Body.String())
	}
}

func securityPhotoStore(t *testing.T) *photoStore {
	t.Helper()
	store, err := openPhotoStore(t.TempDir(), defaultUploadMaxBytes, defaultMaxPhotoPixels)
	if err != nil {
		t.Fatal(err)
	}
	return store
}

func assertNoStoredFiles(t *testing.T, store *photoStore) {
	t.Helper()
	entries, err := os.ReadDir(store.dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatalf("rejected upload wrote files: %v", entries)
	}
}

func writePhotoPart(t *testing.T, writer *multipart.Writer, data []byte) {
	t.Helper()
	part, err := writer.CreateFormFile("photo", "client-name-is-untrusted.png")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write(data); err != nil {
		t.Fatal(err)
	}
}

func multipartUpload(t *testing.T, handler http.Handler, parts func(t *testing.T, writer *multipart.Writer)) *httptest.ResponseRecorder {
	t.Helper()
	body := multipartBody(t, parts)
	return serveUpload(handler, body.contentType, io.NopCloser(bytes.NewReader(body.data)))
}

func multipartUploadWithPhotoMIME(t *testing.T, handler http.Handler, data []byte, contentType string) *httptest.ResponseRecorder {
	t.Helper()
	return multipartUpload(t, handler, func(t *testing.T, writer *multipart.Writer) {
		t.Helper()
		header := textproto.MIMEHeader{}
		header.Set("Content-Disposition", `form-data; name="photo"; filename="untrusted.png"`)
		header.Set("Content-Type", contentType)
		part, err := writer.CreatePart(header)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write(data); err != nil {
			t.Fatal(err)
		}
	})
}

type encodedMultipart struct {
	data        []byte
	contentType string
}

func multipartBody(t *testing.T, parts func(t *testing.T, writer *multipart.Writer)) encodedMultipart {
	t.Helper()
	buffer := &bytes.Buffer{}
	writer := multipart.NewWriter(buffer)
	parts(t, writer)
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return encodedMultipart{data: buffer.Bytes(), contentType: writer.FormDataContentType()}
}

func serveUpload(handler http.Handler, contentType string, body io.ReadCloser) *httptest.ResponseRecorder {
	recorder := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/api/photos", body)
	req.Header.Set("Content-Type", contentType)
	handler.ServeHTTP(recorder, req)
	return recorder
}

func pngIHDR(width, height uint32) []byte {
	data := make([]byte, 25)
	binary.BigEndian.PutUint32(data[:4], 13)
	copy(data[4:8], "IHDR")
	binary.BigEndian.PutUint32(data[8:12], width)
	binary.BigEndian.PutUint32(data[12:16], height)
	data[16] = 8
	data[17] = 2
	checksum := crc32.ChecksumIEEE(data[4:21])
	binary.BigEndian.PutUint32(data[21:25], checksum)
	return append([]byte("\x89PNG\r\n\x1a\n"), data...)
}

func jpegBytes(t *testing.T) []byte {
	t.Helper()
	data := image.NewRGBA(image.Rect(0, 0, 2, 3))
	data.Set(0, 0, color.RGBA{R: 0xff, A: 0xff})
	buffer := &bytes.Buffer{}
	if err := jpeg.Encode(buffer, data, nil); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func gifBytes(t *testing.T) []byte {
	t.Helper()
	data := image.NewPaletted(image.Rect(0, 0, 2, 3), color.Palette{color.Transparent, color.RGBA{G: 0xff, A: 0xff}})
	data.SetColorIndex(0, 0, 1)
	buffer := &bytes.Buffer{}
	if err := gif.Encode(buffer, data, nil); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

type gatedBody struct {
	*bytes.Reader
	started chan struct{}
	release <-chan struct{}
	once    sync.Once
}

func newGatedBody(data []byte, release <-chan struct{}) *gatedBody {
	return &gatedBody{Reader: bytes.NewReader(data), started: make(chan struct{}), release: release}
}

func (body *gatedBody) Read(data []byte) (int, error) {
	body.once.Do(func() {
		close(body.started)
		<-body.release
	})
	return body.Reader.Read(data)
}

func (body *gatedBody) Close() error { return nil }

type countingReadCloser struct {
	io.ReadCloser
	reads int
}

func (body *countingReadCloser) Read(data []byte) (int, error) {
	body.reads++
	return body.ReadCloser.Read(data)
}
