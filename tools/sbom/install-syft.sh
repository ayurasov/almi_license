#!/usr/bin/env bash
# Syft of a pinned version, checked by its SHA-256 (docs/dependencies.md), into .tools/.
#   tools/sbom/install-syft.sh      prints the path of the binary
set -euo pipefail

version=1.54.1
sha256=c069905b391cc4c20a5ba65ad5c10be2a7ba074f8ea6ad203e24d14e303dad47 # syft_1.54.1_linux_amd64.tar.gz
root=$(cd "$(dirname "$0")/../.." && pwd)
dir="$root/.tools/syft-$version"
if [[ ! -x "$dir/syft" ]]; then
  mkdir -p "$dir"
  archive="$dir/syft.tar.gz"
  curl -fsSL -o "$archive" \
    "https://github.com/anchore/syft/releases/download/v$version/syft_${version}_linux_amd64.tar.gz"
  echo "$sha256  $archive" | sha256sum -c --quiet -
  tar -xzf "$archive" -C "$dir" syft
  rm "$archive"
fi
echo "$dir/syft"
