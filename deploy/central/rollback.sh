#!/usr/bin/env bash
# Back to the version before the last upgrade: its image tag and the backup taken by upgrade.sh.
set -euo pipefail
cd "$(dirname "$0")"
[[ -s previous/backup ]] || { echo "[rollback] ./previous is empty" >&2; exit 1; }
backup="$(< previous/backup)"
docker compose down
cp previous/.env .env
docker compose up -d --wait db
docker compose run --rm -e RESTORE_RESET_SCHEMA=1 --entrypoint /ops/restore.sh backup "/var/backups/almi/$(basename "$backup")"
docker compose run --rm migrate
docker compose up -d --wait
./check.sh
