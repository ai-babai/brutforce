package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"lct-eval/internal/eval"
)

func runClient(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	mode := fs.String("source", "api", "api or archive")
	suiteVersion := fs.String("suite-version", "v1", "suite version for API source")
	base := fs.String("base", "", "evaluation URL, e.g. https://host/vision")
	archive := fs.String("archive", "", "downloaded suite ZIP for archive mode")
	token := fs.String("token", "", "participant token, defaults to LCT_EVAL_PARTICIPANT_TOKEN")
	endpoint := fs.String("endpoint", "http://127.0.0.1:8080/v1/eval/predict", "solution prediction endpoint")
	track := fs.String("track", "service", "service or retrieval")
	baskets := fs.String("baskets", "", "comma-separated basket IDs (default all for track)")
	id := fs.String("submission-id", "", "unique id")
	solution := fs.String("solution", "", "solution name")
	solVersion := fs.String("solution-version", "", "solution version")
	commit := fs.String("commit", "", "solution commit")
	configHash := fs.String("config-hash", "", "solution config hash")
	weightsVersion := fs.String("weights-version", "", "weights version")
	catalogVersion := fs.String("catalog-version", "", "catalog version")
	by := fs.String("by", "agent", "display name")
	output := fs.String("output", "", "optional submission JSON path")
	noSubmit := fs.Bool("no-submit", false, "write predictions without posting to the scoring server (requires -output)")
	fs.Parse(args)
	if *id == "" || *solution == "" || *solVersion == "" || (*base == "" && (*mode == "api" || !*noSubmit)) {
		fatal("-submission-id -solution -solution-version required; -base required for API source or submission")
	}
	if *noSubmit && *output == "" {
		fatal("-no-submit requires -output")
	}
	if *token == "" {
		*token = os.Getenv("LCT_EVAL_PARTICIPANT_TOKEN")
	}
	if *token == "" && !*noSubmit {
		fatal("token required")
	}
	baseURL := strings.TrimRight(*base, "/")
	httpClient := &http.Client{Timeout: 30 * time.Second}
	var suite eval.Suite
	var files map[string][]byte
	var e error
	if *mode == "api" {
		var suites []eval.Suite
		e = getJSON(httpClient, baseURL+"/api/baskets", *token, &suites)
		if e != nil {
			fatal(e.Error())
		}
		for _, candidate := range suites {
			if candidate.Version == *suiteVersion {
				suite = candidate
				break
			}
		}
		if suite.Version == "" {
			fatal("suite version not found")
		}
	} else if *mode == "archive" {
		if *archive == "" {
			fatal("-archive required")
		}
		suite, files, e = readArchive(*archive)
		if e != nil {
			fatal(e.Error())
		}
		if suite.Version != *suiteVersion {
			fatal("archive suite version does not match -suite-version")
		}
	} else {
		fatal("source must be api or archive")
	}
	selected := []string{}
	if *baskets != "" {
		selected = strings.Split(*baskets, ",")
	} else {
		for _, b := range suite.Baskets {
			if b.Track == *track {
				selected = append(selected, b.ID)
			}
		}
	}
	sub := eval.Submission{ID: *id, SuiteVersion: suite.Version, SuiteHash: suite.Hash, Track: *track, BasketIDs: selected, Solution: eval.Solution{Name: *solution, Version: *solVersion, Commit: optionalString(*commit), ConfigHash: optionalString(*configHash), WeightsVersion: optionalString(*weightsVersion), CatalogVersion: optionalString(*catalogVersion)}, SubmittedBy: *by, Results: []eval.Result{}}
	cases, e := eval.Selected(suite, sub)
	if e != nil {
		fatal(e.Error())
	}
	predictClient := &http.Client{Transport: &http.Transport{DialContext: (&net.Dialer{Timeout: 5 * time.Second}).DialContext}, Timeout: 10 * time.Second}
	for _, c := range cases {
		var image []byte
		if *mode == "archive" {
			image = files[c.ImagePath]
		} else {
			image, e = getBytes(httpClient, baseURL+"/api/baskets/"+suite.Version+"/cases/"+c.ID+"/image", *token)
			if e != nil {
				fatal(e.Error())
			}
		}
		h := sha256.Sum256(image)
		if hex.EncodeToString(h[:]) != c.ImageSHA256 {
			fatal("image hash mismatch: " + c.ID)
		}
		result := predict(predictClient, *endpoint, c, image, *track)
		sub.Results = append(sub.Results, result)
		fmt.Fprintf(os.Stderr, "%s %s %dms\n", c.ID, result.Status, result.LatencyMS)
	}
	payload, _ := json.MarshalIndent(sub, "", "  ")
	if *output != "" {
		if e = os.WriteFile(*output, append(payload, '\n'), 0600); e != nil {
			fatal(e.Error())
		}
	}
	if *noSubmit {
		fmt.Println("predictions written to", *output)
		return
	}
	req, e := http.NewRequest("POST", baseURL+"/api/submissions", bytes.NewReader(payload))
	if e != nil {
		fatal(e.Error())
	}
	req.Header.Set("Authorization", "Bearer "+*token)
	req.Header.Set("Content-Type", "application/json")
	resp, e := httpClient.Do(req)
	if e != nil {
		fatal(e.Error())
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if resp.StatusCode != 200 && resp.StatusCode != 201 {
		fatal(fmt.Sprintf("submit %s: %s", resp.Status, string(b)))
	}
	fmt.Println(string(b))
}
func optionalString(v string) *string {
	if v == "" {
		return nil
	}
	return &v
}
func getBytes(client *http.Client, url, token string) ([]byte, error) {
	req, e := http.NewRequest("GET", url, nil)
	if e != nil {
		return nil, e
	}
	req.Header.Set("Authorization", "Bearer "+token)
	resp, e := client.Do(req)
	if e != nil {
		return nil, e
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("GET %s: %s", url, resp.Status)
	}
	return io.ReadAll(io.LimitReader(resp.Body, 50<<20))
}
func getJSON(client *http.Client, url, token string, v any) error {
	b, e := getBytes(client, url, token)
	if e != nil {
		return e
	}
	return json.Unmarshal(b, v)
}
func readArchive(path string) (eval.Suite, map[string][]byte, error) {
	r, e := zip.OpenReader(path)
	if e != nil {
		return eval.Suite{}, nil, e
	}
	defer r.Close()
	files := map[string][]byte{}
	for _, f := range r.File {
		if f.UncompressedSize64 > 50<<20 {
			return eval.Suite{}, nil, errors.New("archive file too large")
		}
		rc, e := f.Open()
		if e != nil {
			return eval.Suite{}, nil, e
		}
		b, e := io.ReadAll(io.LimitReader(rc, 50<<20))
		rc.Close()
		if e != nil {
			return eval.Suite{}, nil, e
		}
		files[f.Name] = b
	}
	var suite eval.Suite
	for p, b := range files {
		if strings.HasPrefix(p, "baskets/") && strings.HasSuffix(p, ".json") {
			if e = json.Unmarshal(b, &suite); e != nil {
				return suite, nil, e
			}
			break
		}
	}
	if suite.Version == "" {
		return suite, nil, errors.New("suite manifest missing")
	}
	h, e := eval.ComputeHash(suite)
	if e != nil {
		return suite, nil, e
	}
	if h != suite.Hash {
		return suite, nil, errors.New("suite hash mismatch")
	}
	for _, c := range suite.Cases {
		b, ok := files[c.ImagePath]
		if !ok {
			return suite, nil, fmt.Errorf("missing image %s", c.ID)
		}
		sum := sha256.Sum256(b)
		if hex.EncodeToString(sum[:]) != c.ImageSHA256 {
			return suite, nil, fmt.Errorf("image hash mismatch %s", c.ID)
		}
	}
	return suite, files, nil
}
func predict(client *http.Client, endpoint string, c eval.Case, img []byte, track string) (result eval.Result) {
	start := time.Now()
	result = eval.Result{CaseID: c.ID, Status: "error"}
	defer func() { result.LatencyMS = time.Since(start).Milliseconds() }()
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	ext := filepath.Ext(c.ImagePath)
	if ext == "" {
		ext = ".jpg"
	}
	part, e := writer.CreateFormFile("image", c.ID+ext)
	if e != nil {
		return result
	}
	part.Write(img)
	writer.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, e := http.NewRequestWithContext(ctx, "POST", endpoint, &body)
	if e != nil {
		return result
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, e := client.Do(req)
	if e != nil {
		if errors.Is(e, context.DeadlineExceeded) || os.IsTimeout(e) || ctx.Err() == context.DeadlineExceeded {
			result.Status = "timeout"
		}
		return result
	}
	defer resp.Body.Close()
	b, e := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if e != nil {
		if errors.Is(e, context.DeadlineExceeded) || os.IsTimeout(e) || ctx.Err() == context.DeadlineExceeded {
			result.Status = "timeout"
		}
		return result
	}
	if resp.StatusCode != 200 && resp.StatusCode != 201 {
		return result
	}
	b = bytes.TrimSpace(b)
	var obj map[string]json.RawMessage
	if len(b) > 0 && b[0] == '[' {
		var arr []map[string]json.RawMessage
		if json.Unmarshal(b, &arr) != nil || len(arr) == 0 {
			return result
		}
		obj = arr[0]
	} else if json.Unmarshal(b, &obj) != nil {
		return result
	}
	json.Unmarshal(obj["slug"], &result.Prediction.Slug)
	json.Unmarshal(obj["action"], &result.Prediction.Action)
	json.Unmarshal(obj["ranked_slugs"], &result.Prediction.RankedSlugs)
	if track == "retrieval" && len(result.Prediction.RankedSlugs) == 0 && result.Prediction.Slug != "" {
		result.Prediction.RankedSlugs = []string{result.Prediction.Slug}
	}
	if track == "service" && result.Prediction.Slug == "" && result.Prediction.Action == "" {
		return result
	}
	if track == "retrieval" && len(result.Prediction.RankedSlugs) == 0 {
		return result
	}
	result.Status = "ok"
	return result
}
