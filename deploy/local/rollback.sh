#!/usr/bin/env bash
# Back to the version before the last upgrade (E15-06): its files from ./previous, its images
# (still loaded), and the backup taken by upgrade.sh — changes made after the upgrade are lost.
#   ./rollback.sh
set -euo pipefail
cd "$(dirname "$0")"
[[ -s previous/backup ]] || { echo "[rollback] no previous version: ./previous is empty" >&2; exit 1; }
backup="$(< previous/backup)"
echo "[rollback] files of the previous version, data of $backup"
docker compose down
cp previous/{docker-compose.yml,gateway.conf.template,install.sh,upgrade.sh,check.sh,backup.sh,restore.sh,.env} .
rm -rf ops && cp -r previous/ops ops
# The database goes back to the copy taken before the migrations of the new version.
docker compose up -d --wait db
docker compose run --rm -e RESTORE_RESET_SCHEMA=1 --entrypoint /ops/restore.sh backup "/var/backups/almi/$(basename "$backup")"
docker compose run --rm migrate
docker compose up -d --wait
./check.sh
