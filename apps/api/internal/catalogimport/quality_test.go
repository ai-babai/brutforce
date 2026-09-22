package catalogimport

import (
	"brutforce-behavior-demo/apps/api/internal/catalogmodel"
	"strings"
	"testing"
)

func TestQualityReportDoesNotMarkUnexecutedCasesPassed(t *testing.T) {
	r := Validate(Options{PackageDir: t.TempDir(), Version: "bad"}, "test", Snapshot{}, nil)
	if r.Status != "failed" {
		t.Fatalf("unexpected status: %#v", r)
	}
	failed := false
	for _, c := range r.Cases {
		failed = failed || c.Status == "failed"
		if c.Status == "passed" {
			t.Fatalf("unexecuted %s was passed", c.ID)
		}
	}
	if !failed {
		t.Fatal("failure was not assigned to a case")
	}
}

func TestDQ011RejectsRemovalApprovalOutsideBaseline(t *testing.T) {
	root := writePackage(t, wineJSON(`"x":"y"`), "")
	previous := Snapshot{Wines: []catalogmodel.Wine{{ID: "synthetic-wine"}}}
	r := Validate(Options{PackageDir: root, Version: "v2"}, "test", previous, map[string]bool{"never-in-baseline": true})
	if r.Status != "failed" {
		t.Fatal("approval for an unknown baseline ID was accepted")
	}
	dq := r.Cases[len(r.Cases)-1]
	if dq.ID != "DQ011" || len(dq.Failures) == 0 || !strings.Contains(dq.Failures[0].Slug, "not in baseline") {
		t.Fatalf("unexpected DQ011 result: %#v", dq)
	}
}
