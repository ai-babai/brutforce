#!/usr/bin/env bash
# Build a self-contained Linux amd64 release archive and its external checksum.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 OUTPUT_DIRECTORY" >&2
  exit 64
fi

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output=$1
revision=$(git -C "$root" rev-parse HEAD)
case "$output" in
  /*) ;;
  *) output="$PWD/$output" ;;
esac
parent=$(dirname "$output")
mkdir -p "$parent"
parent=$(cd "$parent" && pwd -P)
output="$parent/$(basename "$output")"
case "$output" in "$root"|"$root"/*) echo "OUTPUT_DIRECTORY must be outside the repository" >&2; exit 64;; esac
[ ! -e "$output" ] || { echo "OUTPUT_DIRECTORY already exists: $output" >&2; exit 64; }

stage=$(mktemp -d "$parent/.brutforce-release.XXXXXX")
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT
mkdir -p "$stage/package/evidence" "$stage/package/web" "$stage/package/migrations"
evidence_dir=${RELEASE_EVIDENCE_DIR:-"$stage/package/evidence"}
mkdir -p "$evidence_dir"

CHECK_EVIDENCE_DIR="$evidence_dir" GIT_REVISION="$revision" "$root/deploy/check.sh"
if [ "$evidence_dir" != "$stage/package/evidence" ]; then
  cp -R "$evidence_dir"/. "$stage/package/evidence/"
fi

cd "$root"
build_go() {
  local output_file=$1
  local target=$2
  (cd "$root/apps/api" && GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -buildvcs=false -ldflags='-s -w' -o "$stage/package/$output_file" "$target")
}
build_go brutforce-api .
build_go reference-engine ./cmd/reference-engine
build_go roman-conformance ./cmd/roman-conformance
build_go catalog-migrate ./cmd/catalog-migrate
npm --prefix apps/web run build
cp -R apps/web/dist/. "$stage/package/web/"
cp -R apps/api/migrations/. "$stage/package/migrations/"
printf '%s\n' "$revision" > "$stage/package/REVISION"
node -e '
const fs=require("fs"), path=require("path");
const [web,revision]=process.argv.slice(1);
fs.writeFileSync(path.join(web,"release.json"),JSON.stringify({revision,mode:"reference",catalogVersion:"demo-v1",modelVersion:"reference-demo-v1",synthetic:true},null,2)+"\n");
' "$stage/package/web" "$revision"

node -e '
const fs=require("fs"), crypto=require("crypto"), path=require("path");
const [dir,revision]=process.argv.slice(1);
function walk(folder){return fs.readdirSync(folder,{withFileTypes:true}).flatMap(e=>{
 const p=path.join(folder,e.name); return e.isDirectory()?walk(p):[p];
});}
const files=walk(dir).filter(p=>path.basename(p)!=="manifest.json").sort().map(p=>({
 path:path.relative(dir,p).split(path.sep).join("/"),
 sha256:crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex")
}));
fs.writeFileSync(path.join(dir,"manifest.json"),JSON.stringify({
 schemaVersion:1, revision, mode:"reference", catalogVersion:"demo-v1",
 modelVersion:"reference-demo-v1", synthetic:true,
 builtAt:new Date().toISOString(), files
},null,2)+"\n");
' "$stage/package" "$revision"

archive="release-$revision.tar.gz"
tar -C "$stage/package" -czf "$stage/$archive" .
checksum=$(sha256sum "$stage/$archive" | awk '{print $1}')
printf '%s  %s\n' "$checksum" "$archive" > "$stage/$archive.sha256"
mv "$stage" "$output"
trap - EXIT
echo "$output/$archive"
