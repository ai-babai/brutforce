package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"lct-eval/internal/eval"
)

type app struct {
	root                string
	vision              *visionCatalog
	suite               eval.Suite
	gold                eval.Gold
	participant, review string
	mu                  sync.Mutex
	runs                map[string]eval.Report
	order               []string
	runsPath            string
	tailCorrupt         bool
}

func main() {
	if len(os.Args) < 2 {
		fatal("usage: lct-eval serve|seal|run ...")
	}
	switch os.Args[1] {
	case "serve":
		serve(os.Args[2:])
	case "seal":
		seal(os.Args[2:])
	case "run":
		runClient(os.Args[2:])
	default:
		fatal("unknown command")
	}
}
func fatal(s string) { fmt.Fprintln(os.Stderr, s); os.Exit(1) }
func seal(args []string) {
	fs := flag.NewFlagSet("seal", flag.ExitOnError)
	root := fs.String("data", "", "suite data directory")
	fs.Parse(args)
	if *root == "" {
		fatal("-data required")
	}
	sp := filepath.Join(*root, "baskets", "v1.json")
	gp := filepath.Join(*root, "private", "gold-v1.json")
	var s eval.Suite
	var g eval.Gold
	readJSONFile(sp, &s)
	readJSONFile(gp, &g)
	if s.Version == "" || g.Version != s.Version {
		fatal("version mismatch")
	}
	g.Hash = ""
	s.Hash = ""
	gh, e := eval.ComputeGoldHash(g)
	if e != nil {
		fatal(e.Error())
	}
	s.GoldHash = gh
	sh, e := eval.ComputeHash(s)
	if e != nil {
		fatal(e.Error())
	}
	s.Hash = sh
	g.Hash = sh
	writeJSONFile(sp, s)
	writeJSONFile(gp, g)
	if e := os.Chmod(gp, 0600); e != nil {
		fatal(e.Error())
	}
	if _, e := eval.LoadSuite(sp); e != nil {
		fatal(e.Error())
	}
	if _, e := eval.LoadGold(gp, s); e != nil {
		fatal(e.Error())
	}
	fmt.Println("suite_hash", sh, "gold_hash", gh)
}
func readJSONFile(path string, v any) {
	b, e := os.ReadFile(path)
	if e != nil {
		fatal(e.Error())
	}
	if e = json.Unmarshal(b, v); e != nil {
		fatal(e.Error())
	}
}
func writeJSONFile(path string, v any) {
	b, e := json.MarshalIndent(v, "", "  ")
	if e != nil {
		fatal(e.Error())
	}
	b = append(b, '\n')
	if e = os.WriteFile(path, b, 0644); e != nil {
		fatal(e.Error())
	}
}
func serve(args []string) {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	root := fs.String("data", "", "suite data directory")
	addr := fs.String("listen", "127.0.0.1:8124", "listen address")
	web := fs.String("web", "web", "web asset directory")
	visionRoot := fs.String("vision-data", os.Getenv("LCT_EVAL_VISION_DATA"), "separate vision image data directory")
	fs.Parse(args)
	if *root == "" {
		fatal("-data required")
	}
	participant := os.Getenv("LCT_EVAL_PARTICIPANT_TOKEN")
	review := os.Getenv("LCT_EVAL_REVIEW_TOKEN")
	if participant == "" || review == "" || participant == review {
		fatal("set distinct LCT_EVAL_PARTICIPANT_TOKEN and LCT_EVAL_REVIEW_TOKEN")
	}
	s, e := eval.LoadSuite(filepath.Join(*root, "baskets", "v1.json"))
	if e != nil {
		fatal(e.Error())
	}
	g, e := eval.LoadGold(filepath.Join(*root, "private", "gold-v1.json"), s)
	if e != nil {
		fatal(e.Error())
	}
	a := &app{root: *root, suite: s, gold: g, participant: participant, review: review, runs: map[string]eval.Report{}, runsPath: filepath.Join(*root, "runs.jsonl")}
	if *visionRoot != "" {
		if sameOrNestedRoot(*root, *visionRoot) {
			fatal("-vision-data must be separate from the sealed evaluation data")
		}
		a.vision = &visionCatalog{root: *visionRoot}
		if _, e := a.vision.snapshot(); e != nil {
			fatal("vision data: " + e.Error())
		}
	}
	if e = a.loadRuns(); e != nil {
		fatal(e.Error())
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok\n")) })
	mux.HandleFunc("GET /api/auth", a.authInfo)
	mux.HandleFunc("GET /api/baskets", a.baskets)
	mux.HandleFunc("GET /api/baskets/{version}/download", a.download)
	mux.HandleFunc("GET /api/baskets/{version}/catalog", a.catalog)
	mux.HandleFunc("GET /api/baskets/{version}/cases/{id}", a.caseInfo)
	mux.HandleFunc("GET /api/baskets/{version}/cases/{id}/image", a.image)
	mux.HandleFunc("POST /api/submissions", a.submit)
	mux.HandleFunc("GET /api/runs", a.listRuns)
	mux.HandleFunc("GET /api/runs/{id}", a.run)
	mux.HandleFunc("GET /api/data/slugs", a.dataSlugs)
	mux.HandleFunc("GET /api/data/facets", a.dataFacets)
	mux.HandleFunc("GET /api/data/images", a.dataImages)
	mux.HandleFunc("GET /api/data/images/{id}", a.dataImageInfo)
	mux.HandleFunc("GET /api/data/images/{id}/image", a.dataImage)
	mux.HandleFunc("GET /api/data/images/{id}/thumbnail", a.dataThumbnail)
	mux.Handle("GET /data/", http.StripPrefix("/data/", http.FileServer(http.Dir(filepath.Join(*web, "gallery")))))
	mux.Handle("/", http.FileServer(http.Dir(*web)))
	srv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second, MaxHeaderBytes: 1 << 16}
	log.Printf("lct-eval listening %s suite=%s cases=%d", *addr, s.Hash, len(s.Cases))
	log.Fatal(srv.ListenAndServe())
}
func (a *app) role(r *http.Request) string {
	h := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if h == "" {
		return ""
	}
	if subtle.ConstantTimeCompare([]byte(h), []byte(a.review)) == 1 {
		return "review"
	}
	if subtle.ConstantTimeCompare([]byte(h), []byte(a.participant)) == 1 {
		return "participant"
	}
	return ""
}
func (a *app) require(w http.ResponseWriter, r *http.Request) string {
	role := a.role(r)
	if role == "" {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	}
	return role
}
func jsonOut(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
func (a *app) authInfo(w http.ResponseWriter, r *http.Request) {
	role := a.role(r)
	if role == "" {
		role = "public"
	}
	jsonOut(w, 200, map[string]string{"role": role})
}
func (a *app) baskets(w http.ResponseWriter, r *http.Request) {
	jsonOut(w, 200, []eval.Suite{a.suite})
}
func (a *app) versionOK(w http.ResponseWriter, r *http.Request) bool {
	if r.PathValue("version") != a.suite.Version {
		http.NotFound(w, r)
		return false
	}
	return true
}
func (a *app) lookupCase(id string) *eval.Case {
	for i := range a.suite.Cases {
		if a.suite.Cases[i].ID == id {
			return &a.suite.Cases[i]
		}
	}
	return nil
}
func (a *app) caseInfo(w http.ResponseWriter, r *http.Request) {
	if !a.versionOK(w, r) {
		return
	}
	c := a.lookupCase(r.PathValue("id"))
	if c == nil {
		http.NotFound(w, r)
		return
	}
	jsonOut(w, 200, c)
}
func (a *app) image(w http.ResponseWriter, r *http.Request) {
	if !a.versionOK(w, r) {
		return
	}
	c := a.lookupCase(r.PathValue("id"))
	if c == nil {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Cache-Control", "private, max-age=3600")
	http.ServeFile(w, r, filepath.Join(a.root, filepath.FromSlash(c.ImagePath)))
}
func (a *app) catalog(w http.ResponseWriter, r *http.Request) {
	if !a.versionOK(w, r) {
		return
	}
	if a.suite.CatalogPath == "" {
		http.NotFound(w, r)
		return
	}
	http.ServeFile(w, r, filepath.Join(a.root, filepath.FromSlash(a.suite.CatalogPath)))
}
func (a *app) download(w http.ResponseWriter, r *http.Request) {
	if !a.versionOK(w, r) {
		return
	}
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", "attachment; filename=\"lct-eval-"+a.suite.Version+".zip\"")
	w.Header().Set("Cache-Control", "no-store")
	z := zip.NewWriter(w)
	defer z.Close()
	paths := []string{"baskets/" + a.suite.Version + ".json"}
	if a.suite.CatalogPath != "" {
		paths = append(paths, a.suite.CatalogPath)
	}
	seen := map[string]bool{}
	for _, c := range a.suite.Cases {
		paths = append(paths, c.ImagePath)
	}
	for _, p := range paths {
		if seen[p] {
			continue
		}
		seen[p] = true
		f, e := z.Create(p)
		if e != nil {
			return
		}
		data, e := os.ReadFile(filepath.Join(a.root, filepath.FromSlash(p)))
		if e != nil {
			return
		}
		if _, e = f.Write(data); e != nil {
			return
		}
	}
}
func (a *app) loadRuns() error {
	f, e := os.Open(a.runsPath)
	if errors.Is(e, os.ErrNotExist) {
		return nil
	}
	if e != nil {
		return e
	}
	defer f.Close()
	reader := bufio.NewReader(f)
	for {
		line, e := reader.ReadBytes('\n')
		if e != nil && e != io.EOF {
			return e
		}
		if len(line) == 0 {
			break
		}
		if line[len(line)-1] != '\n' {
			a.tailCorrupt = true
			break
		}
		var report eval.Report
		if json.Unmarshal(bytes.TrimSpace(line), &report) != nil || report.RunID == "" || a.runs[report.RunID].RunID != "" {
			a.tailCorrupt = true
			break
		}
		a.runs[report.RunID] = report
		a.order = append(a.order, report.RunID)
		if e == io.EOF {
			break
		}
	}
	if a.tailCorrupt {
		log.Printf("WARNING: invalid runs.jsonl tail; prior runs readable, new submissions disabled until repaired")
	}
	return nil
}
func hashPayload(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func (a *app) submit(w http.ResponseWriter, r *http.Request) {
	if a.require(w, r) == "" {
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 2<<20)
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	var sub eval.Submission
	if e := dec.Decode(&sub); e != nil {
		http.Error(w, e.Error(), 400)
		return
	}
	var trailing any
	if dec.Decode(&trailing) != io.EOF {
		http.Error(w, "trailing JSON", 400)
		return
	}
	report, e := eval.Score(a.suite, a.gold, sub)
	if e != nil {
		http.Error(w, e.Error(), 400)
		return
	}
	report.PayloadSHA256 = hashPayload(sub)
	report.RunID = sub.ID
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.tailCorrupt {
		http.Error(w, "run history tail needs repair", 503)
		return
	}
	if old, ok := a.runs[sub.ID]; ok {
		if old.PayloadSHA256 != report.PayloadSHA256 {
			http.Error(w, "submission_id conflict", 409)
			return
		}
		jsonOut(w, 200, sanitize(old, a.role(r) == "review", a.gold, sub.Track))
		return
	}
	report.ReceivedAt = time.Now().UTC().Format(time.RFC3339Nano)
	b, e := json.Marshal(report)
	if e != nil {
		http.Error(w, e.Error(), 500)
		return
	}
	f, e := os.OpenFile(a.runsPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if e != nil {
		http.Error(w, e.Error(), 500)
		return
	}
	_, e = f.Write(append(b, '\n'))
	if e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e == nil {
		e = closeErr
	}
	if e != nil {
		http.Error(w, e.Error(), 500)
		return
	}
	a.runs[sub.ID] = report
	a.order = append(a.order, sub.ID)
	jsonOut(w, 201, sanitize(report, a.role(r) == "review", a.gold, sub.Track))
}
func sanitize(rep eval.Report, review bool, g eval.Gold, track string) eval.Report {
	if !review {
		return rep
	}
	gm := map[string]eval.GoldCase{}
	for _, c := range g.Cases {
		gm[c.ID] = c
	}
	for i := range rep.Cases {
		c := gm[rep.Cases[i].CaseID]
		var gt *eval.GoldTrack
		if track == "service" {
			gt = c.Service
		} else {
			gt = c.Retrieval
		}
		if gt != nil {
			rep.Cases[i].ExpectedSlug = gt.ExpectedSlug
			rep.Cases[i].ExpectedAction = gt.ExpectedAction
		}
	}
	return rep
}

// publicReport hides submitted answers and submitter identity. A correct
// prediction would otherwise disclose a private gold answer in public runs.
func publicReport(rep eval.Report) eval.Report {
	rep.Submission.SubmittedBy = ""
	rep.Submission.Results = nil
	rep.Cases = append([]eval.CaseScore(nil), rep.Cases...)
	for i := range rep.Cases {
		rep.Cases[i].Prediction = eval.Prediction{}
		rep.Cases[i].ExpectedSlug = ""
		rep.Cases[i].ExpectedAction = ""
	}
	return rep
}
func (a *app) listRuns(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	out := make([]eval.Report, 0, len(a.order))
	for _, id := range a.order {
		rep := a.runs[id]
		if role := a.role(r); role == "review" {
			rep = sanitize(rep, true, a.gold, rep.Submission.Track)
		} else if role == "" {
			rep = publicReport(rep)
		}
		out = append(out, rep)
	}
	jsonOut(w, 200, out)
}
func (a *app) run(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	rep, ok := a.runs[r.PathValue("id")]
	a.mu.Unlock()
	if !ok {
		http.NotFound(w, r)
		return
	}
	if role := a.role(r); role == "review" {
		rep = sanitize(rep, true, a.gold, rep.Submission.Track)
	} else if role == "" {
		rep = publicReport(rep)
	}
	jsonOut(w, 200, rep)
}
