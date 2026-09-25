package referenceengine

import (
	"strings"
	"testing"
)

func TestSVC008MandatoryWireFieldsAndAdditiveCompatibility(t *testing.T) {
	valid := `{"catalogVersion":"demo-v1","modelVersion":"m1","demo":false,"candidates":[{"id":"demo-merlot-2022","score":0}],"futureMetadata":{"x":1}}`
	got, err := DecodeResponse([]byte(valid))
	if err != nil || got.Demo || len(got.Candidates) != 1 {
		t.Fatalf("valid additive response rejected: %v", err)
	}
	for _, tc := range []struct{ name, body string }{
		{"missing demo", strings.Replace(valid, `"demo":false,`, "", 1)},
		{"null demo", strings.Replace(valid, `"demo":false`, `"demo":null`, 1)},
		{"missing score", strings.Replace(valid, `,"score":0`, "", 1)},
		{"null score", strings.Replace(valid, `"score":0`, `"score":null`, 1)},
		{"null candidates", `{"catalogVersion":"demo-v1","modelVersion":"m","demo":true,"candidates":null}`},
		{"trailing document", valid + ` {}`},
		{"blank model", strings.Replace(valid, `"m1"`, `" "`, 1)},
		{"oversize", valid + strings.Repeat(" ", 64<<10)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := DecodeResponse([]byte(tc.body)); err == nil {
				t.Fatal("invalid wire response accepted")
			}
		})
	}
}
