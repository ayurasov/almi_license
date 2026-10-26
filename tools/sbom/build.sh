#!/usr/bin/env bash
# SBOM of the ALMI deliverables with licences and notices (docs/sbom.md).
#   VERSION=1.0.0 tools/sbom/build.sh [out-dir]          (make sbom; out-dir: dist/sbom)
#
# Needs docker with the images of the release (almi-license:$VERSION, almi-license-console:$VERSION,
# postgres:17, nginx:1.27), uv, console/node_modules (npm ci) and Syft (SYFT, otherwise
# tools/sbom/install-syft.sh). The DL module: VCPKG_INSTALLED=<build>/vcpkg_installed with
# VCPKG_TRIPLET adds its SBOM; SBOMs of the module built elsewhere (the Windows job of CI) are
# taken from <out-dir>/dl/. PARTS limits the run (images, keytool, dl, dev; report always).
# Exit code 1: a component breaks the licence policy (tools/sbom/license-policy.json) or a wheel
# bundles a library that tools/sbom/vendored.json does not describe.
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
here="$root/tools/sbom"
version="${VERSION:?VERSION is required: the tag of the images}"
out=$(mkdir -p "${1:-$root/dist/sbom}" && cd "${1:-$root/dist/sbom}" && pwd)
parts="${PARTS:-images keytool dl dev}"
syft="${SYFT:-$("$here/install-syft.sh")}"
# A fixed place, not mktemp: Syft derives the ids of packages from the path of an environment.
work="$root/.tools/sbom-work"
rm -rf "$work" && mkdir -p "$work"
trap 'rm -rf "$work"' EXIT
export SYFT_CONFIG="$here/syft.yaml"
# The time of the build is the time of the commit: the same commit gives the same files.
epoch="${SOURCE_DATE_EPOCH:-$(git -C "$root" log -1 --format=%ct)}"
timestamp=$(date -u -d "@$epoch" +%Y-%m-%dT%H:%M:%SZ)
sbom() { python3 -I "$here/sbom.py" --timestamp "$timestamp" "$@"; }
want() { [[ " $parts " == *" $1 "* ]]; }
failed=0
mkdir -p "$out/notices" "$out/dl"

scan() { # scan <source> <file> [syft options]
  local source=$1 file=$2
  shift 2
  "$syft" scan "$source" -q -o "cyclonedx-json=$file" "$@"
}

if want images; then
  server="almi-license:$version"
  console="almi-license-console:$version"
  scan "docker:$server" "$work/server.json" --source-name almi-license --source-version "$version"
  sbom finalize --in "$work/server.json" --out "$out/almi-license.cdx.json" --name almi-license \
    --version "$version" --kind application --vendored "$here/vendored.json" --image "$server" \
    --description "Образ сервера лицензирования: Debian (python:3.13-slim), Python 3.13, пакеты Python из server/uv.lock" ||
    failed=1
  sbom notices --image "$server" --out "$out/notices/almi-license-python.txt" \
    --title "Сторонние пакеты Python образа almi-license:$version: тексты лицензий"

  scan "docker:$console" "$work/console-image.json" --source-name almi-license-console --source-version "$version"
  scan "dir:$root/console" "$work/console-lock.json" --exclude './node_modules/**' \
    --override-default-catalogers javascript-lock-cataloger
  sbom finalize --in "$work/console-image.json" "$work/console-lock.json" \
    --out "$out/almi-license-console.cdx.json" --name almi-license-console --version "$version" \
    --kind application --own almi-license-console \
    --description "Образ консоли: Nginx (nginx:1.27) и сборка Vue; пакеты npm — зависимости выполнения из console/package-lock.json, они входят в сборку" ||
    failed=1
  sbom notices --npm-lock "$root/console/package-lock.json" --out "$out/notices/almi-license-console-npm.txt" \
    --title "Сторонние пакеты npm сборки консоли almi-license-console:$version: тексты лицензий"

  # Images of PostgreSQL and Nginx go to customers unchanged in the bundle of a closed network.
  for image in postgres:17 nginx:1.27; do
    name="${image%%:*}"
    scan "docker:$image" "$work/$name.json" --source-name "$name" --source-version "${image#*:}"
    sbom finalize --in "$work/$name.json" --out "$out/$name.cdx.json" --name "$image" \
      --version "${image#*:}" --kind os \
      --description "Сторонний образ без изменений, передаётся в комплекте локального сервера" ||
      failed=1
  done
fi

if want keytool; then
  # The ceremony tool runs offline from its own environment (tools/almi-keytool/README.md).
  UV_PROJECT_ENVIRONMENT="$work/keytool-venv" uv sync -q --frozen --no-dev --project "$root/tools/almi-keytool"
  scan "dir:$work/keytool-venv" "$work/keytool.json" --override-default-catalogers python-installed-package-cataloger
  sbom finalize --in "$work/keytool.json" --out "$out/almi-keytool.cdx.json" --name almi-keytool \
    --version "$version" --kind application --own almi-keytool --vendored "$here/vendored.json" \
    --description "Инструмент церемонии ключей (офлайн-рабочее место): пакеты Python из tools/almi-keytool/uv.lock" ||
    failed=1
  sbom notices --local-python "$work/keytool-venv/bin/python" --own almi-keytool \
    --out "$out/notices/almi-keytool-python.txt" --title "Сторонние пакеты Python almi-keytool: тексты лицензий"
fi

if want dl && [[ -n "${VCPKG_INSTALLED:-}" ]]; then
  triplet="${VCPKG_TRIPLET:-x64-linux}"
  sbom vcpkg --installed "$VCPKG_INSTALLED" --triplet "$triplet" --version "$version" \
    --out "$out/dl/license_module-$triplet.cdx.json" --dev-out "$work/dl-tests-$triplet.json" \
    --notices "$out/notices/license_module-$triplet.txt"
  cp "$work/dl-tests-$triplet.json" "$out/dl/license_module-tests-$triplet.cdx.json"
fi

if want dev; then
  # Development, tests and CI: what the deliverables do not contain.
  delivered=()
  for file in "$out"/*.cdx.json; do [[ "$file" == *-dev.cdx.json ]] || delivered+=("$file"); done
  UV_PROJECT_ENVIRONMENT="$work/server-dev" uv sync -q --frozen --project "$root/server"
  scan "dir:$work/server-dev" "$work/server-dev.json" --override-default-catalogers python-installed-package-cataloger
  SYFT_JAVASCRIPT_INCLUDE_DEV_DEPENDENCIES=true scan "dir:$root/console" "$work/console-dev.json" \
    --exclude './node_modules/**' --override-default-catalogers javascript-lock-cataloger
  dl_tests=("$out"/dl/license_module-tests-*.cdx.json)
  [[ -e "${dl_tests[0]}" ]] || dl_tests=()
  sbom finalize --in "$work/server-dev.json" "$work/console-dev.json" "${dl_tests[@]}" \
    --out "$out/almi-license-dev.cdx.json" --name almi-license-dev --version "$version" --kind dev \
    --own almi-license-server almi-license-console --exclude-from "${delivered[@]}" \
    --description "Разработка, тесты и CI (группа dev server/pyproject.toml, devDependencies консоли, тестовые порты vcpkg); в поставку не входит" ||
    failed=1
fi

# Report of everything in the directory, the DL module of every platform included.
# Deliverables first, development last.
shopt -s nullglob
boms=()
for file in "$out/almi-license.cdx.json" "$out/almi-license-console.cdx.json" "$out"/dl/license_module-x64-*.cdx.json \
  "$out/almi-keytool.cdx.json" "$out/postgres.cdx.json" "$out/nginx.cdx.json" "$out/almi-license-dev.cdx.json"; do
  [[ -f "$file" ]] && boms+=("$file")
done
sbom report "${boms[@]}" --out "$out/sbom-report.md" --csv "$out/sbom-components.csv" \
  --meta "Версия=$version" "Коммит=$(git -C "$root" rev-parse --short HEAD)" "Время сборки=$timestamp" \
  "Syft=$("$syft" version | awk '/^Version:/ {print $2}')" || failed=1
(cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$work/SHA256SUMS")
mv "$work/SHA256SUMS" "$out/SHA256SUMS"
exit "$failed"
