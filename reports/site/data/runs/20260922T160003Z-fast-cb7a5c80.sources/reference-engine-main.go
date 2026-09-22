package main

import (
	"log"
	"net/http"
	"os"
	"time"

	"brutforce-behavior-demo/apps/api/internal/referenceengine"
)

func main() {
	address := os.Getenv("ADDRESS")
	if address == "" {
		address = "127.0.0.1:8101"
	}
	log.Printf("synthetic reference engine listening on %s (demo only; image results make no accuracy claim)", address)
	server := &http.Server{Addr: address, Handler: referenceengine.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 << 10}
	log.Fatal(server.ListenAndServe())
}
