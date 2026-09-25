package main

import (
	_ "embed"
	"net/http"
)

// These assets are deliberately vendored so the private demo does not load API
// documentation code or a validator from a third party at runtime.
// swagger-ui-dist 5.18.2, Apache-2.0: https://www.npmjs.com/package/swagger-ui-dist
//
//go:embed docs/swagger-ui/swagger-ui-bundle.js
var swaggerUIBundle []byte

//go:embed docs/swagger-ui/swagger-ui.css
var swaggerUICSS []byte

//go:embed docs/openapi.json
var openAPISpec []byte

//go:embed docs/demo-search.schema.json
var embeddedDemoSearchSchema []byte

const docsPage = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BrutForce demo API</title>
  <link rel="stylesheet" href="/api/docs/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="/api/docs/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/api/openapi.json",
      dom_id: "#swagger-ui",
      deepLinking: true,
      validatorUrl: null,
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    });
  </script>
</body>
</html>`

func docsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	switch r.URL.Path {
	case "/api/docs":
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		_, _ = w.Write([]byte(docsPage))
	case "/api/docs/":
		http.Redirect(w, r, "/api/docs", http.StatusMovedPermanently)
	case "/api/docs/swagger-ui.css":
		serveEmbeddedAsset(w, "text/css; charset=utf-8", swaggerUICSS)
	case "/api/docs/swagger-ui-bundle.js":
		serveEmbeddedAsset(w, "application/javascript; charset=utf-8", swaggerUIBundle)
	default:
		writeError(w, http.StatusNotFound, "not_found", "API route not found")
	}
}

func openAPIHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	serveEmbeddedAsset(w, "application/json; charset=utf-8", openAPISpec)
}

func demoSearchSchemaHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use GET")
		return
	}
	serveEmbeddedAsset(w, "application/schema+json; charset=utf-8", embeddedDemoSearchSchema)
}

func serveEmbeddedAsset(w http.ResponseWriter, contentType string, body []byte) {
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "no-store")
	_, _ = w.Write(body)
}
