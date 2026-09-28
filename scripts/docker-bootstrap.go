// One-shot named-volume owner setup before dropping privileges for the migrator.
package main

import (
	"log"
	"os"
	"syscall"
)

func main() {
	for _, dir := range []string{"/snapshots", "/data/uploads", "/data/feedback"} {
		if err := os.Chown(dir, 10001, 10001); err != nil {
			log.Fatal("cannot prepare named volume: ", err)
		}
		if err := os.Chmod(dir, 0700); err != nil {
			log.Fatal("cannot restrict named volume: ", err)
		}
	}
	if err := syscall.Setgroups([]int{10001}); err != nil {
		log.Fatal(err)
	}
	if err := syscall.Setgid(10001); err != nil {
		log.Fatal(err)
	}
	if err := syscall.Setuid(10001); err != nil {
		log.Fatal(err)
	}
	if err := syscall.Exec("/usr/local/bin/docker-migrate.sh", []string{"docker-migrate.sh"}, os.Environ()); err != nil {
		log.Fatal(err)
	}
}
