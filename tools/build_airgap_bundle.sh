#!/usr/bin/env bash
# Build the bundle of a local server for a closed network (E15-04; document 7, section 9).
#   VERSION=1.0.0 TRUST_ROOTS="kid:pub" [BUILD_IMAGES=0] [SBOM_DIR=dist/sbom] tools/build_airgap_bundle.sh [out dir]
# Images: the server and the console built here, postgres:17 and nginx:1.27 as pinned in the
# compose file; everything is saved with docker save. SHA256SUMS covers every file; its signature
# (SHA256SUMS.sig) is made with the ALMI release key outside CI (question 44).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="${VERSION:?VERSION is required}"
: "${TRUST_ROOTS:?TRUST_ROOTS (kid:pub of the ALMI roots) is required}"
out="${1:-$root/dist}"
name="almi-license-local-$version"
dir="$out/$name"
postgres="postgres:17"
nginx="nginx:1.27"

rm -rf "$dir" && mkdir -p "$dir/images" "$dir/ops" "$dir/docs"
cd "$root"
# BUILD_IMAGES=0 takes the images already built with these tags (a build without registry access).
if [[ "${BUILD_IMAGES:-1}" == "1" ]]; then
  docker build -f deploy/Dockerfile --target runtime --build-arg APP_VERSION="$version" \
    -t "almi-license:$version" .
  docker build -f deploy/console/Dockerfile -t "almi-license-console:$version" .
fi
docker image inspect "$postgres" > /dev/null 2>&1 || docker pull --quiet "$postgres" > /dev/null
docker image inspect "$nginx" > /dev/null 2>&1 || docker pull --quiet "$nginx" > /dev/null
docker save -o "$dir/images/almi-license-$version.tar" "almi-license:$version"
docker save -o "$dir/images/almi-license-console-$version.tar" "almi-license-console:$version"
docker save -o "$dir/images/postgres-17.tar" "$postgres"
docker save -o "$dir/images/nginx-1.27.tar" "$nginx"

cp deploy/local/{docker-compose.yml,gateway.conf.template,install.sh,upgrade.sh,rollback.sh,check.sh,backup.sh,restore.sh} "$dir/"
cp deploy/ops/{backup.sh,restore.sh} "$dir/ops/"
cp docs/operations/airgap-install.md "$dir/docs/install.md"
cp docs/operations/backup.md "$dir/docs/backup.md"
sed -e "s/^ALMI_VERSION=.*/ALMI_VERSION=$version/" -e "s|^TRUST_ROOTS=.*|TRUST_ROOTS=$TRUST_ROOTS|" \
  deploy/local/.env.example > "$dir/.env.example"
chmod +x "$dir"/*.sh "$dir"/ops/*.sh
# SBOM of these images with licences and notices (docs/sbom.md): make sbom with the same VERSION.
if [[ -n "${SBOM_DIR:-}" ]]; then
  sbom_version=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["metadata"]["component"]["version"])' \
    "$SBOM_DIR/almi-license.cdx.json")
  [[ "$sbom_version" == "$version" ]] || { echo "SBOM of $sbom_version, bundle of $version" >&2; exit 1; }
  mkdir -p "$dir/sbom" && cp -r "$SBOM_DIR"/. "$dir/sbom/"
fi

sums="$(mktemp)"
(cd "$dir" && find . -type f -printf '%P\n' | sort | xargs sha256sum) > "$sums"
mv "$sums" "$dir/SHA256SUMS" && chmod 644 "$dir/SHA256SUMS"
tar -C "$out" -czf "$out/$name.tar.gz" "$name"
echo "$out/$name.tar.gz"
