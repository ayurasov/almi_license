#!/usr/bin/env bash
# Encrypted backup of the PostgreSQL database of a central or local server (E15-03).
#
#   DATABASE_URL            postgres://user:password@host:5432/db (from the environment or a secret)
#   BACKUP_DIR              where the copies are kept (default /var/backups/almi)
#   BACKUP_PASSPHRASE_FILE  Docker secret with the passphrase; never an argument or a variable
#   BACKUP_KEEP_DAYS        retention (default 30)
#   SERVER_KEY_FILE         optional: the key of a local server, copied separately, encrypted
#
# The dump is pg_dump -Fc encrypted with gpg (AES-256, integrity protected); SHA-256 sums sit
# next to it. On success the UTC time goes to $BACKUP_DIR/last-success (metric of /metrics).
set -euo pipefail
umask 077

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_PASSPHRASE_FILE:?BACKUP_PASSPHRASE_FILE is required}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/almi}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
[ -r "$BACKUP_PASSPHRASE_FILE" ] || { echo "backup: passphrase file is not readable" >&2; exit 1; }

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$BACKUP_DIR/almi-$stamp.dump.gpg"
partial="$dump.partial"

encrypt() {
  gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
    --symmetric --cipher-algo AES256 --output "$1"
}

trap 'rm -f "$partial" "$BACKUP_DIR"/*.partial' EXIT
pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" | encrypt "$partial"
mv "$partial" "$dump"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$dump")" > "$(basename "$dump").sha256")

if [ -n "${SERVER_KEY_FILE:-}" ]; then
  key="$BACKUP_DIR/almi-$stamp.server-key.gpg"
  encrypt "$key.partial" < "$SERVER_KEY_FILE"
  mv "$key.partial" "$key"
fi

find "$BACKUP_DIR" -maxdepth 1 -name 'almi-*' -type f -mtime "+$KEEP_DAYS" -delete
date -u +%s > "$BACKUP_DIR/last-success.partial"
mv "$BACKUP_DIR/last-success.partial" "$BACKUP_DIR/last-success"
echo "backup: $(basename "$dump")"
