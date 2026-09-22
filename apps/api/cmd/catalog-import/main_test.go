package main

import (
	"os/exec"
	"strings"
	"testing"
)

func TestCompareIDsDoesNotRequireSnapshotOut(t *testing.T) {
	cmd := exec.Command("go", "run", ".",
		"-compare-ids",
		"-package", t.TempDir(),
		"-version", "test-version",
		"-accepted-report", "missing-report.json",
		"-validator-version", "test-validator",
		"-previous-snapshot", "missing-snapshot.json",
	)
	output, err := cmd.CombinedOutput()
	if err == nil {
		t.Fatal("invalid comparison unexpectedly succeeded")
	}
	message := string(output)
	if strings.Contains(message, "snapshot-out") {
		t.Fatalf("compare-ids was incorrectly routed through import guard: %s", message)
	}
	if !strings.Contains(message, "previous snapshot is invalid") {
		t.Fatalf("compare-ids did not reach comparison mode: %s", message)
	}
}
