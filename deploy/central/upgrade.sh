#!/usr/bin/env bash
# Upgrade the central server to the checked-out version of the repository (docs/deployment.md).
#   git -C ../.. pull && NEW_VERSION=x.y.z ./upgrade.sh
# A backup first; the previous image tag and .env stay in ./previous for rollback.sh.
set -euo pipefail
cd "$(dirname "$0")"
repo="$(cd ../.. && pwd)"
# shellcheck disable=SC1091
source .env
previous="$ALMI_VERSION"
next="${NEW_VERSION:?NEW_VERSION is required (the version to build)}"
echo "[upgrade] $previous -> $next: backup"
./backup.sh
copies=(backups/almi-*.dump.gpg)  # named by UTC time: the last one is the newest
rm -rf previous && mkdir previous && cp .env previous/ && printf '%s\n' "${copies[-1]}" > previous/backup
docker build -q -f "$repo/deploy/Dockerfile" --target runtime --build-arg APP_VERSION="$next" \
  -t "almi-license:$next" "$repo" > /dev/null
docker build -q -f "$repo/deploy/console/Dockerfile" -t "almi-license-console:$next" "$repo" > /dev/null
sed -i "s/^ALMI_VERSION=.*/ALMI_VERSION=$next/" .env
if ! docker compose run --rm migrate; then
  echo "[upgrade] migration failed: back to $previous" >&2
  ./rollback.sh
  exit 1
fi
docker compose up -d --wait
docker compose run --rm api manage loadcatalog
./check.sh
echo "[upgrade] done; ./rollback.sh returns to $previous with the data of ${copies[-1]}"
