#!/usr/bin/env bash
# Restore a backup of ./backups: ./restore.sh backups/almi-<time>.dump.gpg
set -euo pipefail
cd "$(dirname "$0")"
dump="${1:?usage: restore.sh backups/almi-<time>.dump.gpg}"
docker compose stop api worker gateway
docker compose run --rm --entrypoint /ops/restore.sh backup "/var/backups/almi/$(basename "$dump")"
docker compose run --rm migrate
docker compose run --rm api manage verify_audit
docker compose up -d --wait
./check.sh
