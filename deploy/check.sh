#!/usr/bin/env bash
# Strict, reproducible release gate. It deliberately refuses partial fast reports.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
revision=${GIT_REVISION:-$(git -C "$root" rev-parse HEAD)}
evidence_dir=${CHECK_EVIDENCE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/brutforce-check.XXXXXX")}
mkdir -p "$evidence_dir"
checks_file=${CHECK_EVIDENCE_FILE:-"$evidence_dir/checks.json"}
db_results="$evidence_dir/database-test.jsonl"
db_metadata="$evidence_dir/database-metadata.json"
mkdir -p "$(dirname "$checks_file")"

for command in go node npm python3; do
  command -v "$command" >/dev/null || { echo "required command is unavailable: $command" >&2; exit 1; }
done

go_version=$(go env GOVERSION)
node_version=$(node --version)
node -e '
const [goVersion,nodeVersion]=process.argv.slice(1);
const go=/^go(\d+)\.(\d+)/.exec(goVersion);
const node=/^v(\d+)\.(\d+)/.exec(nodeVersion);
if (!go || go[1] !== "1" || Number(go[2]) < 23) process.exitCode=1;
const supportedNode=node && ((Number(node[1]) === 20 && Number(node[2]) >= 19) || (Number(node[1]) === 22 && Number(node[2]) >= 12) || Number(node[1]) > 22);
if (!supportedNode) process.exitCode=1;
' "$go_version" "$node_version" || { echo "requires Go >= 1.23 and Node >= 20.19" >&2; exit 1; }

: "${DATABASE_URL:?DATABASE_URL is required for the PostgreSQL integration gate}"
: "${MIGRATION_DATABASE_URL:?MIGRATION_DATABASE_URL is required for the PostgreSQL integration gate}"

cd "$root"
python3 -m unittest discover -s deploy -p 'test_*.py'
npm --prefix apps/web ci

reference_address=127.0.0.1:18101
reference_log="$evidence_dir/reference-engine.log"
reference_bin=$(mktemp "${TMPDIR:-/tmp}/brutforce-reference-engine.XXXXXX")
(cd apps/api && go build -trimpath -buildvcs=false -o "$reference_bin" ./cmd/reference-engine)
ADDRESS="$reference_address" "$reference_bin" >"$reference_log" 2>&1 &
reference_pid=$!
cleanup_reference() { kill "$reference_pid" 2>/dev/null || true; wait "$reference_pid" 2>/dev/null || true; rm -f "$reference_bin"; }
trap cleanup_reference EXIT
node -e '
const net=require("net"); const deadline=Date.now()+20000;
(function wait(){ const socket=net.connect(18101,"127.0.0.1");
 socket.once("connect",()=>{socket.end(); process.exit(0)});
 socket.once("error",()=>{socket.destroy(); if(Date.now()>=deadline) process.exit(1); setTimeout(wait,100)});
})();
' || { echo "reference engine did not start; log: $reference_log" >&2; exit 1; }
(cd apps/api && SEARCH_SERVICE_URL="http://$reference_address" RECOMMENDATION_SERVICE_URL="http://$reference_address" CATALOG_VERSION=demo-v1 go run ./cmd/roman-conformance) | tee "$evidence_dir/roman-conformance.log"
cleanup_reference
trap - EXIT

db_started=$(node -e 'process.stdout.write(String(Date.now()))')
set +e
(cd apps/api &&
  go test -tags=integration -count=1 -json -run '^TestDB000' . &&
  go test -tags=integration -count=1 -json -run '^Test(DB00[1-5]|CAT009)' .) >"$db_results" 2>&1
db_exit=$?
set -e
db_finished=$(node -e 'process.stdout.write(String(Date.now()))')
if [ "$db_exit" -ne 0 ]; then
  echo "PostgreSQL integration gate failed; evidence: $db_results" >&2
  exit "$db_exit"
fi

node -e '
const fs=require("fs");
const [out,revision,wall]=process.argv.slice(1);
fs.writeFileSync(out, JSON.stringify({
  schemaVersion: 1,
  revision,
  command: "go test -tags=integration -count=1 -json -run ^TestDB000 . && go test -tags=integration -count=1 -json -run ^Test(DB00[1-5]|CAT009) .",
  wallMs: Number(wall),
  environment: "PostgreSQL integration; synthetic demo catalog only"
}, null, 2)+"\n");
' "$db_metadata" "$revision" "$((db_finished - db_started))"

fast_stdout="$evidence_dir/fast-check.stdout.json"
set +e
DB_TEST_RESULTS_FILE="$db_results" \
DB_TEST_METADATA_FILE="$db_metadata" \
GIT_REVISION="$revision" \
node scripts/run-fast-checks.mjs | tee "$fast_stdout"
fast_exit=${PIPESTATUS[0]}
set -e
report_path=$(node -e 'const fs=require("fs"); const o=JSON.parse(fs.readFileSync(process.argv[1],"utf8")); if (!o.report) process.exit(1); process.stdout.write(o.report)' "$fast_stdout")
report_file="$root/$report_path"
[ -f "$report_file" ] || { echo "fast report was not created: $report_path" >&2; exit 1; }
cp "$report_file" "$evidence_dir/fast-report.json"
[ "$fast_exit" -eq 0 ] || { echo "Fast checks failed; see retained fast-report.json" >&2; exit "$fast_exit"; }

node -e '
const fs=require("fs");
const [out,report,revision,goVersion,nodeVersion]=process.argv.slice(1);
const run=JSON.parse(fs.readFileSync(report,"utf8"));
if (run.status !== "passed") {
  console.error(`strict release gate rejected fast-report status: ${run.status}`);
  process.exit(1);
}
if (!run.databaseEvidence || run.databaseEvidence.valid !== true) {
  console.error("strict release gate rejected missing or invalid PostgreSQL evidence");
  process.exit(1);
}
fs.writeFileSync(out, JSON.stringify({
  schemaVersion: 1,
  revision,
  status: "passed",
  mode: "reference",
  catalogVersion: "demo-v1",
  modelVersion: "reference-demo-v1",
  synthetic: true,
  commands: ["python3 -m unittest discover -s deploy -p test_*.py", "npm --prefix apps/web ci", "go build ./cmd/reference-engine + roman-conformance against localhost", "go test -tags=integration -count=1 -json -run ^TestDB000 . && go test -tags=integration -count=1 -json -run ^Test(DB00[1-5]|CAT009) .", "node scripts/run-fast-checks.mjs"],
  versions: {go: goVersion, node: nodeVersion},
  databaseEvidence: run.databaseEvidence,
  fastReport: "fast-report.json"
}, null, 2)+"\n");
' "$checks_file" "$report_file" "$revision" "$go_version" "$node_version"

echo "strict release checks passed: $checks_file"
