#!/usr/bin/env bash
# The guides as documents to hand over: DOCX (pandoc) and PDF (LibreOffice) with the screenshots.
#   tools/build_guides.sh [out-dir]      (make guides)
# The title and the contents are in each guide itself, so pandoc adds neither.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/dist/guides}
mkdir -p "$out"
cd "$root/docs"

build() {
  local source=$1 name=$2
  pandoc "$source" --from gfm --to docx --resource-path=. --metadata lang=ru-RU -o "$out/$name.docx"
  soffice --headless --convert-to pdf --outdir "$out" "$out/$name.docx" > /dev/null
  echo "ok   $out/$name.docx, $out/$name.pdf"
}

build user-guide.md almi-license-operator-guide
build deployment.md almi-license-admin-guide
