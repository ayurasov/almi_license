#!/usr/bin/env bash
# Restore an encrypted backup of backup.sh into a database and check it (E15-03).
#
#   restore.sh <almi-YYYYMMDDTHHMMSSZ.dump.gpg>
#   DATABASE_URL            target database (it is replaced: --clean)
#   BACKUP_PASSPHRASE_FILE  the same Docker secret as for the backup
#
# The SHA-256 sum is checked first; after pg_restore the script prints the number of rows of the
# main tables for the check against the source. The server then checks the audit chain with
# "manage.py verify_audit" (docs/operations/backup.md).
set -euo pipefail
umask 077

dump="${1:?usage: restore.sh <backup.dump.gpg>}"
if [[ -n "${DATABASE_URL_FILE:-}" ]]; then DATABASE_URL="$(< "$DATABASE_URL_FILE")"; fi
: "${DATABASE_URL:?DATABASE_URL or DATABASE_URL_FILE is required}"
: "${BACKUP_PASSPHRASE_FILE:?BACKUP_PASSPHRASE_FILE is required}"

if [ -f "$dump.sha256" ]; then
  (cd "$(dirname "$dump")" && sha256sum --check --quiet "$(basename "$dump").sha256")
else
  echo "restore: no $dump.sha256, the copy is not checked" >&2
  exit 1
fi

gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
  --decrypt "$dump" | pg_restore --clean --if-exists --no-owner --exit-on-error --dbname="$DATABASE_URL"

for table in licensing_license licensing_licensekey activation_activation audit_auditevent; do
  count="$(psql --no-psqlrc --tuples-only --no-align --dbname="$DATABASE_URL" -c "SELECT count(*) FROM $table")"
  echo "restore: $table $count"
done
echo "restore: done"
