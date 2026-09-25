package main

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"testing"
)

type failingCatalog struct{}

func (failingCatalog) List(context.Context) ([]wine, error) {
	return nil, errors.New("database unavailable")
}
func (failingCatalog) Search(context.Context, *string) ([]wine, error) {
	return nil, errors.New("database unavailable")
}

func TestDB006CatalogUnavailableReturnsStructured503(t *testing.T) {
	handler := newHandlerWithCatalog("", nil, failingCatalog{})
	for _, item := range []struct {
		method, path, body string
	}{
		{http.MethodGet, "/v2/catalog", ""},
		{http.MethodPost, "/v1/search", `{"scenario":"exact"}`},
	} {
		response := request(t, handler, item.method, item.path, item.body)
		decoded := decodeResponse(t, response)
		if response.Code != http.StatusServiceUnavailable || decoded.Error == nil || decoded.Error.Code != "catalog_unavailable" {
			t.Fatalf("%s %s: status=%d response=%+v", item.method, item.path, response.Code, decoded)
		}
	}
}

func TestDB006ConfiguredDatabaseDoesNotFallBackOrExposeURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://user:secret-password@localhost:invalid-port/catalog")
	_, _, err := openConfiguredCatalog(context.Background())
	if !errors.Is(err, errCatalogUnavailable) || strings.Contains(err.Error(), "secret-password") {
		t.Fatalf("configured database error=%v", err)
	}
}
