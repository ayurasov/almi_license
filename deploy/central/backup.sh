#!/usr/bin/env bash
# Encrypted backup of the central server into ./backups (deploy/ops/backup.sh in the postgres image).
set -euo pipefail
cd "$(dirname "$0")"
exec docker compose run --rm backup
