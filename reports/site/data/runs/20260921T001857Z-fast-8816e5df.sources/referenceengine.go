// Package referenceengine provides a deterministic synthetic Roman reference service.
package referenceengine

import (
	"bytes"
	"encoding/json"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"math"
	"mime"
	"net/http"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

const CatalogVersion = "demo-v1"

var IDs = []string{"demo-cabernet-sauvignon-2023", "demo-merlot-2022", "demo-saperavi-2021", "demo-pinot-noir-2020", "demo-krasnostop-2022", "demo-shiraz-2021", "demo-cabernet-franc-2019", "demo-tsimlyansky-black-2023"}
var names = []string{"каберне совиньон", "мерло", "саперави", "пино нуар", "красностоп", "шираз", "каберне фран", "цимлянский чёрный"}

type Candidate struct {
	ID    string  `json:"id"`
	Score float64 `json:"score"`
}
type Response struct {
	CatalogVersion string      `json:"catalogVersion"`
	ModelVersion   string      `json:"modelVersion"`
	Demo           bool        `json:"demo"`
	Candidates     []Candidate `json:"candidates"`
	SelectedID     string      `json:"selectedId,omitempty"`
}

func Handler() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("/v1/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			errJSON(w, 405, "method_not_allowed")
			return
		}
		write(w, 200, map[string]any{"ok": true, "demo": true})
	})
	m.HandleFunc("/v1/search/text", text)
	m.HandleFunc("/v1/search/image", imageSearch)
	m.HandleFunc("/v1/recommendations", recommendations)
	m.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) { errJSON(w, 404, "not_found") })
	return m
}
func text(w http.ResponseWriter, r *http.Request) {
	echoRequestID(w, r)
	if r.Method != http.MethodPost {
		errJSON(w, 405, "method_not_allowed")
		return
	}
	var x struct {
		Query          string `json:"query"`
		CatalogVersion string `json:"catalogVersion"`
		Limit          *int   `json:"limit"`
	}
	if !decode(r, &x) || control(x.Query) || strings.TrimSpace(x.Query) == "" {
		errJSON(w, 400, "invalid_request")
		return
	}
	if x.CatalogVersion != CatalogVersion {
		errJSON(w, 409, "catalog_version_mismatch")
		return
	}
	limit := 5
	if x.Limit != nil {
		limit = *x.Limit
	}
	if limit < 1 || limit > 10 {
		errJSON(w, 400, "invalid_limit")
		return
	}
	out := rank(limit, x.Query)
	if len(out.Candidates) > 0 {
		out.SelectedID = out.Candidates[0].ID
	}
	write(w, 200, out)
}
func imageSearch(w http.ResponseWriter, r *http.Request) {
	echoRequestID(w, r)
	if r.Method != http.MethodPost {
		errJSON(w, 405, "method_not_allowed")
		return
	}
	media, _, e := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if e != nil || media != "multipart/form-data" {
		errJSON(w, 400, "invalid_request")
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 11<<20)
	if r.ParseMultipartForm(11<<20) != nil {
		errJSON(w, 400, "invalid_request")
		return
	}
	defer r.MultipartForm.RemoveAll()
	if len(r.MultipartForm.File) != 1 || len(r.MultipartForm.File["image"]) != 1 || len(r.MultipartForm.Value["catalogVersion"]) != 1 || len(r.MultipartForm.Value["limit"]) > 1 || len(r.MultipartForm.Value) > 2 {
		errJSON(w, 400, "invalid_request")
		return
	}
	f, _, e := r.FormFile("image")
	if e != nil {
		errJSON(w, 400, "invalid_image")
		return
	}
	defer f.Close()
	data, e := io.ReadAll(io.LimitReader(f, 10<<20+1))
	if e != nil || len(data) > 10<<20 {
		errJSON(w, 400, "invalid_image")
		return
	}
	c, format, e := image.DecodeConfig(bytes.NewReader(data))
	if e != nil || (format != "png" && format != "jpeg" && format != "gif") || c.Width < 1 || c.Height < 1 || c.Width > 12000 || c.Height > 12000 || int64(c.Width)*int64(c.Height) > 25000000 {
		errJSON(w, 400, "invalid_image")
		return
	}
	if _, _, e = image.Decode(bytes.NewReader(data)); e != nil {
		errJSON(w, 400, "invalid_image")
		return
	}
	if r.FormValue("catalogVersion") != CatalogVersion {
		errJSON(w, 409, "catalog_version_mismatch")
		return
	}
	limit := 5
	if raw := r.FormValue("limit"); raw != "" {
		limit, e = strconv.Atoi(raw)
	}
	if e != nil || limit < 1 || limit > 10 {
		errJSON(w, 400, "invalid_limit")
		return
	}
	out := rank(limit, "")
	out.SelectedID = out.Candidates[0].ID
	write(w, 200, out)
}
func recommendations(w http.ResponseWriter, r *http.Request) {
	echoRequestID(w, r)
	if r.Method != http.MethodPost {
		errJSON(w, 405, "method_not_allowed")
		return
	}
	var x struct {
		WineID         string `json:"wineId"`
		CatalogVersion string `json:"catalogVersion"`
		Limit          *int   `json:"limit"`
	}
	if !decode(r, &x) {
		errJSON(w, 400, "invalid_request")
		return
	}
	if !known(x.WineID) {
		errJSON(w, 404, "wine_not_found")
		return
	}
	if x.CatalogVersion != CatalogVersion {
		errJSON(w, 409, "catalog_version_mismatch")
		return
	}
	limit := 5
	if x.Limit != nil {
		limit = *x.Limit
	}
	if limit < 1 || limit > 10 {
		errJSON(w, 400, "invalid_limit")
		return
	}
	out := Response{CatalogVersion: CatalogVersion, ModelVersion: "reference-demo-v1", Demo: true, Candidates: []Candidate{}}
	for _, id := range IDs {
		if id != x.WineID && len(out.Candidates) < limit {
			out.Candidates = append(out.Candidates, Candidate{id, 1 - float64(len(out.Candidates))*.1})
		}
	}
	write(w, 200, out)
}
func rank(limit int, q string) Response {
	out := Response{CatalogVersion: CatalogVersion, ModelVersion: "reference-demo-v1", Demo: true, Candidates: []Candidate{}}
	q = strings.ToLower(strings.TrimSpace(q))
	for index, id := range IDs {
		if q == "" || strings.Contains(strings.ToLower(id), q) || strings.Contains(names[index], q) {
			out.Candidates = append(out.Candidates, Candidate{id, 1 - float64(len(out.Candidates))*.1})
			if len(out.Candidates) == limit {
				break
			}
		}
	}
	return out
}
func decode(r *http.Request, target any) bool {
	defer r.Body.Close()
	media, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" {
		return false
	}
	data, err := io.ReadAll(io.LimitReader(r.Body, (64<<10)+1))
	if err != nil || len(data) > 64<<10 || !utf8.Valid(data) {
		return false
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(data, &fields) != nil || fields == nil {
		return false
	}
	for _, raw := range fields {
		if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
			return false
		}
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	return d.Decode(target) == nil
}

func control(s string) bool {
	for _, r := range s {
		if unicode.IsControl(r) {
			return true
		}
	}
	return false
}
func known(id string) bool {
	for _, x := range IDs {
		if x == id {
			return true
		}
	}
	return false
}
func write(w http.ResponseWriter, s int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(s)
	_ = json.NewEncoder(w).Encode(v)
}
func errJSON(w http.ResponseWriter, s int, c string) {
	write(w, s, map[string]any{"error": map[string]string{"code": c, "message": c}})
}
func echoRequestID(w http.ResponseWriter, r *http.Request) {
	if id := r.Header.Get("X-Request-ID"); validRequestID(id) {
		w.Header().Set("X-Request-ID", id)
	}
}
func validRequestID(id string) bool {
	if id == "" || len(id) > 64 {
		return false
	}
	for _, r := range id {
		if !(r == '-' || r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9') {
			return false
		}
	}
	return true
}
func ValidateResponse(r Response, v, source string, sel bool) error {
	if r.CatalogVersion != v || r.ModelVersion == "" || len(r.ModelVersion) > 128 || r.Candidates == nil || len(r.Candidates) > 10 {
		return strconv.ErrSyntax
	}
	seen := map[string]bool{}
	last := 1.
	for i, x := range r.Candidates {
		if !known(x.ID) || seen[x.ID] || x.ID == source || math.IsNaN(x.Score) || math.IsInf(x.Score, 0) || x.Score < 0 || x.Score > 1 || (i > 0 && x.Score > last) {
			return strconv.ErrSyntax
		}
		seen[x.ID] = true
		last = x.Score
	}
	if (!sel && r.SelectedID != "") || (r.SelectedID != "" && !seen[r.SelectedID]) {
		return strconv.ErrSyntax
	}
	return nil
}
