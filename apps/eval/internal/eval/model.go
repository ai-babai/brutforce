package eval

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

type Basket struct {
	ID          string `json:"basket_id"`
	Track       string `json:"track"`
	Priority    string `json:"priority,omitempty"`
	Title       string `json:"title,omitempty"`
	Description string `json:"description,omitempty"`
	Readiness   string `json:"readiness,omitempty"`
	TargetCount int    `json:"target_count,omitempty"`
}
type Case struct {
	ID               string   `json:"case_id"`
	ImagePath        string   `json:"image_path"`
	ImageSHA256      string   `json:"image_sha256"`
	OriginKind       string   `json:"origin_kind"`
	ReferenceDerived bool     `json:"reference_derived"`
	SceneGroupID     string   `json:"scene_group_id,omitempty"`
	BasketIDs        []string `json:"basket_ids"`
	Tracks           []string `json:"tracks"`
}
type Suite struct {
	Version       string   `json:"version"`
	Hash          string   `json:"suite_hash"`
	GoldHash      string   `json:"gold_hash"`
	CatalogPath   string   `json:"catalog_path,omitempty"`
	CatalogSHA256 string   `json:"catalog_sha256,omitempty"`
	Cases         []Case   `json:"cases"`
	Baskets       []Basket `json:"baskets"`
}
type GoldCase struct {
	ID             string          `json:"case_id"`
	Service        *GoldTrack      `json:"service,omitempty"`
	Retrieval      *GoldTrack      `json:"retrieval,omitempty"`
	Verified       bool            `json:"verified"`
	UngradedReason string          `json:"ungraded_reason,omitempty"`
	ReviewedBy     string          `json:"reviewed_by,omitempty"`
	Evidence       json.RawMessage `json:"evidence,omitempty"`
}
type GoldTrack struct {
	ExpectedAction string `json:"expected_action,omitempty"`
	ExpectedSlug   string `json:"expected_slug,omitempty"`
}
type Gold struct {
	Version string     `json:"version"`
	Hash    string     `json:"suite_hash"`
	Cases   []GoldCase `json:"cases"`
}
type Solution struct {
	Name           string  `json:"name"`
	Version        string  `json:"version"`
	Commit         *string `json:"commit"`
	ConfigHash     *string `json:"config_hash"`
	WeightsVersion *string `json:"weights_version"`
	CatalogVersion *string `json:"catalog_version"`
}
type Prediction struct {
	Action      string   `json:"action,omitempty"`
	Slug        string   `json:"slug,omitempty"`
	RankedSlugs []string `json:"ranked_slugs,omitempty"`
}
type Result struct {
	CaseID     string     `json:"case_id"`
	Status     string     `json:"status"`
	Prediction Prediction `json:"prediction"`
	LatencyMS  int64      `json:"latency_ms"`
}
type Submission struct {
	ID           string   `json:"submission_id"`
	SuiteVersion string   `json:"suite_version"`
	SuiteHash    string   `json:"suite_hash"`
	Track        string   `json:"track"`
	BasketIDs    []string `json:"basket_ids"`
	Solution     Solution `json:"solution"`
	SubmittedBy  string   `json:"submitted_by"`
	Results      []Result `json:"results"`
}
type CaseScore struct {
	CaseID           string     `json:"case_id"`
	Status           string     `json:"status"`
	OriginKind       string     `json:"origin_kind"`
	ReferenceDerived bool       `json:"reference_derived"`
	BasketIDs        []string   `json:"basket_ids"`
	Graded           bool       `json:"graded"`
	UngradedReason   string     `json:"ungraded_reason,omitempty"`
	Correct          bool       `json:"correct"`
	Rank             int        `json:"rank,omitempty"`
	LatencyMS        int64      `json:"latency_ms,omitempty"`
	Prediction       Prediction `json:"prediction"`
	ExpectedSlug     string     `json:"expected_slug,omitempty"`
	ExpectedAction   string     `json:"expected_action,omitempty"`
}
type Stats struct {
	Graded       int     `json:"graded"`
	CorrectTop1  int     `json:"correct_top1"`
	CorrectTop5  int     `json:"correct_top5"`
	CorrectTop20 int     `json:"correct_top20"`
	MRR          float64 `json:"mrr"`
	Missing      int     `json:"missing"`
	Ungraded     int     `json:"ungraded"`
}
type Report struct {
	RunID             string           `json:"run_id"`
	ReceivedAt        string           `json:"received_at"`
	ScoringVersion    string           `json:"scoring_version"`
	Submission        Submission       `json:"submission"`
	Cases             []CaseScore      `json:"cases"`
	Overall           Stats            `json:"overall"`
	ByOrigin          map[string]Stats `json:"by_origin"`
	ByBasket          map[string]Stats `json:"by_basket"`
	ByReference       map[string]Stats `json:"by_reference"`
	UniqueSceneGroups int              `json:"unique_scene_groups"`
	PayloadSHA256     string           `json:"payload_sha256"`
}

var idRE = regexp.MustCompile(`^[A-Za-z0-9._-]+$`)
var hashRE = regexp.MustCompile(`^[a-f0-9]{64}$`)

func ValidateID(v string) bool { return idRE.MatchString(v) }
func ComputeHash(s Suite) (string, error) {
	s.Hash = ""
	b, e := json.Marshal(s)
	if e != nil {
		return "", e
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:]), nil
}
func ComputeGoldHash(g Gold) (string, error) {
	g.Hash = ""
	b, e := json.Marshal(g)
	if e != nil {
		return "", e
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:]), nil
}
func LoadSuite(path string) (Suite, error) {
	var s Suite
	b, e := os.ReadFile(path)
	if e != nil {
		return s, e
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	if e = dec.Decode(&s); e != nil {
		return s, e
	}
	var trailing any
	if dec.Decode(&trailing) != io.EOF {
		return s, errors.New("trailing suite JSON")
	}
	if e = s.Validate(filepath.Dir(filepath.Dir(path))); e != nil {
		return s, e
	}
	return s, nil
}
func (s Suite) Validate(root string) error {
	if !ValidateID(s.Version) || !hashRE.MatchString(s.Hash) || !hashRE.MatchString(s.GoldHash) {
		return errors.New("invalid suite version or hash")
	}
	h, e := ComputeHash(s)
	if e != nil {
		return e
	}
	if h != s.Hash {
		return fmt.Errorf("suite_hash mismatch: calculated %s", h)
	}
	if len(s.Cases) == 0 || len(s.Baskets) == 0 {
		return errors.New("empty suite")
	}
	bs := map[string]string{}
	for _, b := range s.Baskets {
		if !ValidateID(b.ID) || bs[b.ID] != "" || (b.Track != "service" && b.Track != "retrieval") {
			return errors.New("invalid or duplicate basket id/track")
		}
		bs[b.ID] = b.Track
	}
	cs := map[string]bool{}
	for _, c := range s.Cases {
		if !ValidateID(c.ID) || cs[c.ID] {
			return errors.New("invalid or duplicate case id")
		}
		cs[c.ID] = true
		if !safeRel(c.ImagePath) || !strings.HasPrefix(c.ImagePath, "images/") || !hashRE.MatchString(c.ImageSHA256) {
			return fmt.Errorf("invalid image metadata for %s", c.ID)
		}
		if c.OriginKind != "real" && c.OriginKind != "ai" && c.OriginKind != "augmentation" {
			return fmt.Errorf("invalid origin for %s", c.ID)
		}
		if len(c.BasketIDs) == 0 || len(c.Tracks) == 0 {
			return fmt.Errorf("no basket or track for %s", c.ID)
		}
		seen := map[string]bool{}
		for _, v := range c.BasketIDs {
			if bs[v] == "" || seen[v] {
				return fmt.Errorf("invalid basket on %s", c.ID)
			}
			seen[v] = true
		}
		seen = map[string]bool{}
		for _, v := range c.Tracks {
			if (v != "service" && v != "retrieval") || seen[v] {
				return fmt.Errorf("invalid track on %s", c.ID)
			}
			seen[v] = true
		}
		if len(c.Tracks) != 1 {
			return fmt.Errorf("case %s must have one track", c.ID)
		}
		for _, v := range c.BasketIDs {
			if bs[v] != c.Tracks[0] {
				return fmt.Errorf("basket track mismatch on %s", c.ID)
			}
		}
		p := filepath.Join(root, filepath.FromSlash(c.ImagePath))
		if e := containedFile(root, "images", p); e != nil {
			return fmt.Errorf("%s: %w", c.ID, e)
		}
		data, e := os.ReadFile(p)
		if e != nil {
			return fmt.Errorf("%s: %w", c.ID, e)
		}
		h := sha256.Sum256(data)
		if hex.EncodeToString(h[:]) != c.ImageSHA256 {
			return fmt.Errorf("image hash mismatch for %s", c.ID)
		}
	}
	if s.CatalogPath != "" {
		if !safeRel(s.CatalogPath) || !strings.HasPrefix(s.CatalogPath, "catalog/") || !hashRE.MatchString(s.CatalogSHA256) {
			return errors.New("invalid catalog metadata")
		}
		catalogFile := filepath.Join(root, filepath.FromSlash(s.CatalogPath))
		if e := containedFile(root, "catalog", catalogFile); e != nil {
			return e
		}
		data, e := os.ReadFile(catalogFile)
		if e != nil {
			return e
		}
		h := sha256.Sum256(data)
		if hex.EncodeToString(h[:]) != s.CatalogSHA256 {
			return errors.New("catalog hash mismatch")
		}
	}
	return nil
}
func containedFile(root, subdir, path string) error {
	base, e := filepath.EvalSymlinks(filepath.Join(root, subdir))
	if e != nil {
		return e
	}
	target, e := filepath.EvalSymlinks(path)
	if e != nil {
		return e
	}
	rel, e := filepath.Rel(base, target)
	if e != nil {
		return e
	}
	if rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return errors.New("file resolves outside public directory")
	}
	info, e := os.Stat(target)
	if e != nil {
		return e
	}
	if !info.Mode().IsRegular() {
		return errors.New("not a regular file")
	}
	return nil
}
func safeRel(p string) bool {
	return p != "" && !strings.Contains(p, "\\") && !filepath.IsAbs(p) && filepath.Clean(p) == p && !strings.HasPrefix(p, "../") && p != ".."
}
func LoadGold(path string, s Suite) (Gold, error) {
	var g Gold
	b, e := os.ReadFile(path)
	if e != nil {
		return g, e
	}
	if e = json.Unmarshal(b, &g); e != nil {
		return g, e
	}
	if g.Version != s.Version || g.Hash != s.Hash {
		return g, errors.New("gold suite version/hash mismatch")
	}
	gh, e := ComputeGoldHash(g)
	if e != nil {
		return g, e
	}
	if gh != s.GoldHash {
		return g, errors.New("gold hash mismatch")
	}
	known := map[string]string{}
	for _, c := range s.Cases {
		known[c.ID] = c.Tracks[0]
	}
	seen := map[string]bool{}
	for _, c := range g.Cases {
		if known[c.ID] == "" || seen[c.ID] {
			return g, errors.New("unknown or duplicate gold case")
		}
		seen[c.ID] = true
		if !c.Verified && c.UngradedReason == "" {
			return g, errors.New("unverified case needs ungraded_reason")
		}
		if c.Verified {
			switch known[c.ID] {
			case "service":
				if c.Service == nil || (c.Service.ExpectedAction != "match" && c.Service.ExpectedAction != "no_match" && c.Service.ExpectedAction != "insufficient_information") || (c.Service.ExpectedAction == "match") != (c.Service.ExpectedSlug != "") {
					return g, fmt.Errorf("invalid verified service gold for %s", c.ID)
				}
			case "retrieval":
				if c.Retrieval == nil || c.Retrieval.ExpectedSlug == "" {
					return g, fmt.Errorf("invalid verified retrieval gold for %s", c.ID)
				}
			}
		}
	}
	if len(seen) != len(known) {
		return g, errors.New("gold is missing case entries")
	}
	return g, nil
}
func Selected(s Suite, sub Submission) ([]Case, error) {
	if sub.SuiteVersion != s.Version || sub.SuiteHash != s.Hash {
		return nil, errors.New("suite version/hash mismatch")
	}
	if sub.Track != "service" && sub.Track != "retrieval" {
		return nil, errors.New("invalid track")
	}
	if len(sub.BasketIDs) == 0 {
		return nil, errors.New("no baskets selected")
	}
	bs := map[string]string{}
	for _, b := range s.Baskets {
		bs[b.ID] = b.Track
	}
	selected := map[string]bool{}
	for _, id := range sub.BasketIDs {
		if bs[id] != sub.Track || selected[id] {
			return nil, errors.New("unknown, duplicate, or wrong-track basket id")
		}
		selected[id] = true
	}
	var cases []Case
	for _, c := range s.Cases {
		if len(c.Tracks) != 1 || c.Tracks[0] != sub.Track {
			continue
		}
		for _, id := range c.BasketIDs {
			if selected[id] {
				cases = append(cases, c)
				break
			}
		}
	}
	return cases, nil
}
func ValidateSubmission(s Suite, sub Submission) ([]Case, error) {
	if !ValidateID(sub.ID) || len(sub.ID) > 128 {
		return nil, errors.New("invalid submission id")
	}
	if strings.TrimSpace(sub.Solution.Name) == "" || strings.TrimSpace(sub.Solution.Version) == "" {
		return nil, errors.New("solution name/version required")
	}
	cases, e := Selected(s, sub)
	if e != nil {
		return nil, e
	}
	allowed := map[string]bool{}
	for _, c := range cases {
		allowed[c.ID] = true
	}
	seen := map[string]bool{}
	for _, r := range sub.Results {
		if !allowed[r.CaseID] || seen[r.CaseID] {
			return nil, errors.New("unknown or duplicate case id")
		}
		seen[r.CaseID] = true
		if r.Status != "ok" && r.Status != "error" && r.Status != "timeout" {
			return nil, errors.New("invalid result status")
		}
		if r.LatencyMS < 0 {
			return nil, errors.New("negative latency")
		}
		if r.Status == "ok" {
			if sub.Track == "service" {
				action := r.Prediction.Action
				if action == "" && r.Prediction.Slug != "" {
					action = "match"
				}
				if action != "match" && action != "no_match" && action != "insufficient_information" {
					return nil, errors.New("invalid service action")
				}
				if action == "match" && r.Prediction.Slug == "" {
					return nil, errors.New("match needs slug")
				}
				if action != "match" && r.Prediction.Slug != "" {
					return nil, errors.New("abstention cannot have slug")
				}
			} else if len(r.Prediction.RankedSlugs) == 0 {
				return nil, errors.New("retrieval result needs ranked_slugs")
			}
		}
		if len(r.Prediction.RankedSlugs) > 1000 {
			return nil, errors.New("ranked_slugs too long")
		}
		rankSeen := map[string]bool{}
		for _, slug := range r.Prediction.RankedSlugs {
			if slug == "" || rankSeen[slug] {
				return nil, errors.New("empty or duplicate ranked slug")
			}
			rankSeen[slug] = true
		}
	}
	return cases, nil
}
func Score(s Suite, g Gold, sub Submission) (Report, error) {
	cases, e := ValidateSubmission(s, sub)
	if e != nil {
		return Report{}, e
	}
	gm := map[string]GoldCase{}
	for _, c := range g.Cases {
		gm[c.ID] = c
	}
	rm := map[string]Result{}
	for _, r := range sub.Results {
		rm[r.CaseID] = r
	}
	report := Report{Submission: sub, ScoringVersion: "1", ByOrigin: map[string]Stats{}, ByBasket: map[string]Stats{}, ByReference: map[string]Stats{}}
	scenes := map[string]bool{}
	selectedBaskets := map[string]bool{}
	for _, id := range sub.BasketIDs {
		selectedBaskets[id] = true
	}
	for _, c := range cases {
		if c.SceneGroupID != "" {
			scenes[c.SceneGroupID] = true
		}
		r, ok := rm[c.ID]
		if !ok {
			r = Result{CaseID: c.ID, Status: "not_run"}
		}
		gc := gm[c.ID]
		var gt *GoldTrack
		if sub.Track == "service" {
			gt = gc.Service
		} else {
			gt = gc.Retrieval
		}
		graded := gc.Verified && gt != nil
		expectedAction := ""
		if gt != nil {
			expectedAction = gt.ExpectedAction
			if expectedAction == "" && gt.ExpectedSlug != "" {
				expectedAction = "match"
			}
			if sub.Track == "retrieval" {
				graded = graded && gt.ExpectedSlug != ""
			} else {
				graded = graded && (expectedAction == "match" && gt.ExpectedSlug != "" || expectedAction == "no_match" || expectedAction == "insufficient_information")
			}
		}
		rank := 0
		if graded && r.Status == "ok" {
			if sub.Track == "service" {
				action := r.Prediction.Action
				if action == "" && r.Prediction.Slug != "" {
					action = "match"
				}
				if action == expectedAction && (action != "match" || r.Prediction.Slug == gt.ExpectedSlug) {
					rank = 1
				}
			} else {
				for i, v := range r.Prediction.RankedSlugs {
					if v == gt.ExpectedSlug {
						rank = i + 1
						break
					}
				}
			}
		}
		reason := ""
		if !graded {
			reason = gc.UngradedReason
			if reason == "" {
				reason = "no_verified_gold"
			}
		}
		score := CaseScore{CaseID: c.ID, Status: r.Status, OriginKind: c.OriginKind, ReferenceDerived: c.ReferenceDerived, BasketIDs: c.BasketIDs, Graded: graded, UngradedReason: reason, Correct: rank == 1, Rank: rank, LatencyMS: r.LatencyMS, Prediction: r.Prediction}
		report.Cases = append(report.Cases, score)
		report.Overall = add(report.Overall, score)
		report.ByOrigin[c.OriginKind] = add(report.ByOrigin[c.OriginKind], score)
		ref := "independent"
		if c.ReferenceDerived {
			ref = "reference_derived"
		}
		report.ByReference[ref] = add(report.ByReference[ref], score)
		for _, b := range c.BasketIDs {
			if selectedBaskets[b] {
				report.ByBasket[b] = add(report.ByBasket[b], score)
			}
		}
	}
	report.UniqueSceneGroups = len(scenes)
	report.Overall = meanMRR(report.Overall)
	for key, value := range report.ByOrigin {
		report.ByOrigin[key] = meanMRR(value)
	}
	for key, value := range report.ByBasket {
		report.ByBasket[key] = meanMRR(value)
	}
	for key, value := range report.ByReference {
		report.ByReference[key] = meanMRR(value)
	}
	sort.Slice(report.Cases, func(i, j int) bool { return report.Cases[i].CaseID < report.Cases[j].CaseID })
	return report, nil
}
func meanMRR(s Stats) Stats {
	if s.Graded > 0 {
		s.MRR /= float64(s.Graded)
	}
	return s
}
func add(s Stats, c CaseScore) Stats {
	if !c.Graded {
		s.Ungraded++
		return s
	}
	s.Graded++
	if c.Status == "not_run" {
		s.Missing++
	}
	if c.Rank == 1 {
		s.CorrectTop1++
	}
	if c.Rank > 0 && c.Rank <= 5 {
		s.CorrectTop5++
	}
	if c.Rank > 0 && c.Rank <= 20 {
		s.CorrectTop20++
	}
	if c.Rank > 0 {
		s.MRR += 1 / float64(c.Rank)
	}
	return s
}
