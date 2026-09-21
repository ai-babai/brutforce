// roman-conformance checks a running provider against the demo-v1 wire contract.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
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

	"brutforce-behavior-demo/apps/api/internal/referenceengine"
)

type check struct {
	name, base, method, path, contentType, source string
	body                                          []byte
	status, limit                                 int
	timeout                                       time.Duration
	selected                                      bool
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "FAIL:", err)
		os.Exit(1)
	}
}
func run() error {
	search := os.Getenv("SEARCH_SERVICE_URL")
	recs := os.Getenv("RECOMMENDATION_SERVICE_URL")
	if search == "" {
		search = os.Getenv("ROMAN_SERVICE_URL")
	}
	if recs == "" {
		recs = os.Getenv("ROMAN_SERVICE_URL")
	}
	for _, base := range []string{search, recs} {
		u, err := url.Parse(base)
		if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
			return errors.New("set valid SEARCH_SERVICE_URL and RECOMMENDATION_SERVICE_URL (or ROMAN_SERVICE_URL), without credentials/query/fragment")
		}
	}
	version := os.Getenv("CATALOG_VERSION")
	if version == "" {
		version = referenceengine.CatalogVersion
	}
	if version != referenceengine.CatalogVersion {
		return errors.New("this fixture conformance suite requires catalog demo-v1; prepare a versioned fixture before testing a different catalog")
	}
	source := referenceengine.IDs[0]
	makeJSON := func(v any) []byte { b, _ := json.Marshal(v); return b }
	checks := []check{
		{name: "text", base: search, path: "/v1/search/text", body: makeJSON(map[string]any{"query": "Каберне", "catalogVersion": version, "limit": 2}), status: 200, limit: 2, selected: true},
		{name: "recommendations", base: recs, path: "/v1/recommendations", source: source, body: makeJSON(map[string]any{"wineId": source, "catalogVersion": version, "limit": 2}), status: 200, limit: 2},
		{name: "default-limit", base: search, path: "/v1/search/text", body: makeJSON(map[string]any{"query": "Каберне", "catalogVersion": version}), status: 200, limit: 5, selected: true},
		{name: "blank-query", base: search, path: "/v1/search/text", body: makeJSON(map[string]any{"query": "  ", "catalogVersion": version}), status: 400},
		{name: "invalid-limit", base: search, path: "/v1/search/text", body: makeJSON(map[string]any{"query": "Каберне", "catalogVersion": version, "limit": 0}), status: 400},
		{name: "unsupported-catalog", base: search, path: "/v1/search/text", body: makeJSON(map[string]any{"query": "Каберне", "catalogVersion": "unknown-conformance-version"}), status: 409},
		{name: "unknown-source", base: recs, path: "/v1/recommendations", body: makeJSON(map[string]any{"wineId": "unknown-conformance-id", "catalogVersion": version}), status: 404},
		{name: "wrong-method", base: search, method: http.MethodGet, path: "/v1/search/text", status: 405},
	}
	var tiny bytes.Buffer
	_ = png.Encode(&tiny, image.NewRGBA(image.Rect(0, 0, 2, 2)))
	for _, fixture := range []struct {
		name   string
		data   []byte
		status int
	}{{"valid-image", tiny.Bytes(), 200}, {"invalid-image", []byte("not an image"), 400}} {
		var body bytes.Buffer
		w := multipart.NewWriter(&body)
		part, _ := w.CreateFormFile("image", "test.png")
		_, _ = part.Write(fixture.data)
		_ = w.WriteField("catalogVersion", version)
		_ = w.WriteField("limit", "2")
		_ = w.Close()
		checks = append(checks, check{name: fixture.name, base: search, path: "/v1/search/image", contentType: w.FormDataContentType(), body: body.Bytes(), status: fixture.status, limit: 2, selected: true, timeout: 8 * time.Second})
	}
	client := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	for _, c := range checks {
		if err := execute(client, c, version); err != nil {
			return err
		}
	}
	fmt.Println("PASS wire contract on demo-v1 synthetic fixtures; not an ML quality or load benchmark")
	return nil
}
func execute(client *http.Client, c check, version string) error {
	if c.method == "" {
		c.method = http.MethodPost
	}
	if c.contentType == "" {
		c.contentType = "application/json"
	}
	if c.timeout == 0 {
		c.timeout = time.Second
	}
	scoped := *client
	scoped.Timeout = c.timeout
	req, err := http.NewRequest(c.method, strings.TrimRight(c.base, "/")+c.path, bytes.NewReader(c.body))
	if err != nil {
		return fmt.Errorf("%s: invalid request", c.name)
	}
	req.Header.Set("Content-Type", c.contentType)
	req.Header.Set("X-Request-ID", "conformance-"+c.name)
	start := time.Now()
	res, err := scoped.Do(req)
	if err != nil {
		return fmt.Errorf("%s: transport failed or deadline exceeded", c.name)
	}
	defer res.Body.Close()
	data, err := io.ReadAll(io.LimitReader(res.Body, (64<<10)+1))
	if err != nil || len(data) > 64<<10 {
		return fmt.Errorf("%s: unreadable or oversized response", c.name)
	}
	media, _, err := mime.ParseMediaType(res.Header.Get("Content-Type"))
	if err != nil || media != "application/json" {
		return fmt.Errorf("%s: response must be application/json", c.name)
	}
	if res.StatusCode != c.status {
		return fmt.Errorf("%s: status%d, expected%d", c.name, res.StatusCode, c.status)
	}
	if c.status == 200 {
		result, err := referenceengine.DecodeResponse(data)
		if err != nil {
			return fmt.Errorf("%s: invalid required wire fields", c.name)
		}
		if len(result.Candidates) > c.limit || referenceengine.ValidateResponse(result, version, c.source, c.selected) != nil {
			return fmt.Errorf("%s: response violates rank/ID/version contract", c.name)
		}
		if res.Header.Get("X-Request-ID") != req.Header.Get("X-Request-ID") {
			return fmt.Errorf("%s: request ID not echoed", c.name)
		}
	} else {
		var e struct {
			Error struct {
				Code    string `json:"code"`
				Message string `json:"message"`
			} `json:"error"`
		}
		if json.Unmarshal(data, &e) != nil || strings.TrimSpace(e.Error.Code) == "" || strings.TrimSpace(e.Error.Message) == "" {
			return fmt.Errorf("%s: structured error required", c.name)
		}
	}
	fmt.Printf("PASS %-20s %d %.1fms\n", c.name, res.StatusCode, float64(time.Since(start).Microseconds())/1000)
	return nil
}
