package eval

import "testing"

func fixture() (Suite, Gold) {
	s := Suite{Version: "v1", Hash: "hash", Baskets: []Basket{{ID: "IMG-09", Track: "service"}, {ID: "RET-01", Track: "retrieval"}}, Cases: []Case{
		{ID: "IMG-09-001", OriginKind: "real", SceneGroupID: "scene-1", BasketIDs: []string{"IMG-09"}, Tracks: []string{"service"}},
		{ID: "IMG-09-002", OriginKind: "ai", BasketIDs: []string{"IMG-09"}, Tracks: []string{"service"}},
		{ID: "IMG-09-003", OriginKind: "real", BasketIDs: []string{"IMG-09"}, Tracks: []string{"service"}},
		{ID: "RET-01-001", OriginKind: "augmentation", ReferenceDerived: true, BasketIDs: []string{"RET-01"}, Tracks: []string{"retrieval"}},
	}}
	g := Gold{Version: "v1", Hash: "hash", Cases: []GoldCase{
		{ID: "IMG-09-001", Verified: true, Service: &GoldTrack{ExpectedAction: "match", ExpectedSlug: "wine-a"}},
		{ID: "IMG-09-002", Verified: true, Service: &GoldTrack{ExpectedAction: "no_match"}},
		{ID: "IMG-09-003", Verified: false, UngradedReason: "awaiting human review"},
		{ID: "RET-01-001", Verified: true, Retrieval: &GoldTrack{ExpectedSlug: "wine-r"}},
	}}
	return s, g
}
func serviceSub() Submission {
	return Submission{ID: "run-1", SuiteVersion: "v1", SuiteHash: "hash", Track: "service", BasketIDs: []string{"IMG-09"}, Solution: Solution{Name: "model", Version: "1"}, Results: []Result{{CaseID: "IMG-09-001", Status: "ok", Prediction: Prediction{Slug: "wrong"}}, {CaseID: "IMG-09-002", Status: "ok", Prediction: Prediction{Action: "no_match"}}}}
}
func TestServiceScoreMissingUngradedAndActions(t *testing.T) {
	s, g := fixture()
	r, e := Score(s, g, serviceSub())
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.Graded != 2 || r.Overall.CorrectTop1 != 1 || r.Overall.Ungraded != 1 || r.Overall.Missing != 0 {
		t.Fatalf("bad stats: %+v", r.Overall)
	}
	if r.ByOrigin["ai"].CorrectTop1 != 1 || r.ByOrigin["real"].Ungraded != 1 {
		t.Fatal("origin breakdown wrong")
	}
	sub := serviceSub()
	sub.Results = sub.Results[:1]
	r, e = Score(s, g, sub)
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.Missing != 1 || r.Overall.CorrectTop1 != 0 {
		t.Fatalf("missing disappeared: %+v", r.Overall)
	}
	sub.Results = append(sub.Results, Result{CaseID: "IMG-09-002", Status: "error"})
	r, e = Score(s, g, sub)
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.CorrectTop1 != 0 {
		t.Fatal("error counted as abstention")
	}
}
func TestRetrievalRanksAndReferenceSplit(t *testing.T) {
	s, g := fixture()
	sub := Submission{ID: "run-r", SuiteVersion: "v1", SuiteHash: "hash", Track: "retrieval", BasketIDs: []string{"RET-01"}, Solution: Solution{Name: "ranker", Version: "1"}, Results: []Result{{CaseID: "RET-01-001", Status: "ok", Prediction: Prediction{RankedSlugs: []string{"a", "b", "wine-r"}}}}}
	r, e := Score(s, g, sub)
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.Graded != 1 || r.Overall.CorrectTop1 != 0 || r.Overall.CorrectTop5 != 1 || r.Overall.CorrectTop20 != 1 || r.Overall.MRR != 1.0/3.0 {
		t.Fatalf("wrong retrieval stats %+v", r.Overall)
	}
	if r.ByReference["reference_derived"].Graded != 1 {
		t.Fatal("reference split missing")
	}
}
func TestRejectUnknownDuplicateAndHash(t *testing.T) {
	s, g := fixture()
	_ = g
	sub := serviceSub()
	sub.SuiteHash = "wrong"
	if _, e := ValidateSubmission(s, sub); e == nil {
		t.Fatal("accepted hash")
	}
	sub = serviceSub()
	sub.Results = append(sub.Results, Result{CaseID: "unknown", Status: "ok", Prediction: Prediction{Slug: "x"}})
	if _, e := ValidateSubmission(s, sub); e == nil {
		t.Fatal("accepted unknown")
	}
	sub = serviceSub()
	sub.Results = append(sub.Results, sub.Results[0])
	if _, e := ValidateSubmission(s, sub); e == nil {
		t.Fatal("accepted duplicate")
	}
}
func TestRejectEmptyAbstention(t *testing.T) {
	s, _ := fixture()
	sub := serviceSub()
	sub.Results[1].Prediction = Prediction{}
	if _, e := ValidateSubmission(s, sub); e == nil {
		t.Fatal("empty prediction accepted")
	}
}
func TestRetrievalMissingCountsInMRRDenominator(t *testing.T) {
	s, g := fixture()
	s.Cases = append(s.Cases, Case{ID: "RET-01-002", OriginKind: "real", BasketIDs: []string{"RET-01"}, Tracks: []string{"retrieval"}})
	g.Cases = append(g.Cases, GoldCase{ID: "RET-01-002", Verified: true, Retrieval: &GoldTrack{ExpectedSlug: "wine-b"}})
	sub := Submission{ID: "run-m", SuiteVersion: "v1", SuiteHash: "hash", Track: "retrieval", BasketIDs: []string{"RET-01"}, Solution: Solution{Name: "ranker", Version: "1"}, Results: []Result{{CaseID: "RET-01-001", Status: "ok", Prediction: Prediction{RankedSlugs: []string{"wine-r"}}}}}
	r, e := Score(s, g, sub)
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.Graded != 2 || r.Overall.Missing != 1 || r.Overall.MRR != 0.5 || r.Overall.CorrectTop1 != 1 {
		t.Fatalf("missing excluded: %+v", r.Overall)
	}
}
func TestOverlappingBasketsDoNotDoubleCountOrReportUnselected(t *testing.T) {
	s, g := fixture()
	s.Baskets = append(s.Baskets, Basket{ID: "IMG-10", Track: "service"})
	s.Cases[0].BasketIDs = []string{"IMG-09", "IMG-10"}
	sub := serviceSub()
	r, e := Score(s, g, sub)
	if e != nil {
		t.Fatal(e)
	}
	if r.Overall.Graded != 2 {
		t.Fatalf("double counted: %+v", r.Overall)
	}
	if _, ok := r.ByBasket["IMG-10"]; ok {
		t.Fatal("unselected basket populated")
	}
}
