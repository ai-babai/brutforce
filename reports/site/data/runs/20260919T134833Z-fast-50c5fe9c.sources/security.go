package main

import (
	"mime"
	"net/http"
	"net/url"
	"sync"
	"time"
)

// A global, constant-memory budget: forwarded IP headers cannot bypass it.
// Limits protect this small demo, not a replacement for upstream DDoS protection.
type requestBudget struct {
	mu               sync.Mutex
	tokens           float64
	last             time.Time
	burst, perSecond float64
}

func (b *requestBudget) allow(now time.Time) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.last.IsZero() {
		b.tokens = b.burst
	} else {
		b.tokens += now.Sub(b.last).Seconds() * b.perSecond
		if b.tokens > b.burst {
			b.tokens = b.burst
		}
	}
	b.last = now
	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}
func protectRequests(next http.Handler, now func() time.Time) http.Handler {
	search := &requestBudget{burst: 10, perSecond: 1}
	uploads := &requestBudget{burst: 4, perSecond: 0.2}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "same-origin")
		w.Header().Set("X-Frame-Options", "DENY")
		if r.Method == http.MethodPost && (r.URL.Path == "/api/search" || r.URL.Path == "/api/photos") {
			w.Header().Set("Cache-Control", "no-store")
			if enc := r.Header.Get("Content-Encoding"); enc != "" && enc != "identity" {
				writeError(w, 415, "unsupported_encoding", "compressed request bodies are not supported")
				return
			}
			if origin := r.Header.Get("Origin"); origin != "" {
				u, e := url.Parse(origin)
				if e != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host != r.Host {
					writeError(w, 403, "cross_origin_request", "cross-origin writes are not allowed")
					return
				}
			}
			if r.URL.Path == "/api/search" {
				media, _, e := mime.ParseMediaType(r.Header.Get("Content-Type"))
				if e != nil || media != "application/json" {
					writeError(w, 415, "unsupported_media_type", "use application/json")
					return
				}
			}
			budget := search
			retry := "1"
			if r.URL.Path == "/api/photos" {
				budget = uploads
				retry = "5"
			}
			if !budget.allow(now()) {
				w.Header().Set("Retry-After", retry)
				writeError(w, 429, "rate_limited", "too many requests; try again later")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}
