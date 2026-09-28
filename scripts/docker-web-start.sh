#!/bin/bash
set -euo pipefail
pass=$(cat /run/secrets/app_password)
case "$pass" in *[!0-9a-f]*|'') echo 'app password must be nonempty lowercase hex' >&2; exit 1;; esac
export ADDRESS=127.0.0.1:8098 WEB_ROOT=/app/web UPLOAD_DIR=/data/uploads FEEDBACK_DIR=/data/feedback
DATABASE_URL="postgres://brutforce_app:${pass}@postgres:5432/brutforce?sslmode=disable" /usr/local/bin/api & api_pid=$!
unset pass
proxy_pid=
cleanup() { kill "$api_pid" ${proxy_pid:+"$proxy_pid"} 2>/dev/null || :; wait "$api_pid" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
/usr/local/bin/web-proxy & proxy_pid=$!
wait -n "$api_pid" "$proxy_pid" || exit 1
exit 1  # either long-running process exited unexpectedly
