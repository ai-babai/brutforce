package referenceengine

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"unicode/utf8"
)

// DecodeResponse validates mandatory wire fields without rejecting additive fields.
// Catalog membership/order is checked separately with ValidateResponse or the app catalog.
func DecodeResponse(data []byte) (Response, error) {
	invalid := errors.New("invalid ranked response")
	var fields map[string]json.RawMessage
	if len(data) > 64<<10 || !utf8.Valid(data) || json.Unmarshal(data, &fields) != nil || fields == nil {
		return Response{}, invalid
	}
	for _, key := range []string{"catalogVersion", "modelVersion", "demo", "candidates"} {
		raw := bytes.TrimSpace(fields[key])
		if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
			return Response{}, invalid
		}
	}
	var result Response
	if json.Unmarshal(data, &result) != nil || result.Candidates == nil || len(result.Candidates) > 10 {
		return Response{}, invalid
	}
	for _, value := range []string{result.CatalogVersion, result.ModelVersion} {
		if strings.TrimSpace(value) == "" || utf8.RuneCountInString(value) > 128 {
			return Response{}, invalid
		}
	}
	if raw, ok := fields["selectedId"]; ok {
		if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) || result.SelectedID == "" || utf8.RuneCountInString(result.SelectedID) > 128 {
			return Response{}, invalid
		}
	}
	var candidates []map[string]json.RawMessage
	if json.Unmarshal(fields["candidates"], &candidates) != nil {
		return Response{}, invalid
	}
	for i, candidate := range candidates {
		for _, key := range []string{"id", "score"} {
			raw := bytes.TrimSpace(candidate[key])
			if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
				return Response{}, invalid
			}
		}
		if strings.TrimSpace(result.Candidates[i].ID) == "" || utf8.RuneCountInString(result.Candidates[i].ID) > 128 {
			return Response{}, invalid
		}
	}
	return result, nil
}
