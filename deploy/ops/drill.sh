#!/usr/bin/env bash
# Restore drill (E15-03): back up the source, restore into a scratch database, compare rows.
#
#   SOURCE_URL   postgres://…/almi_license        TARGET_URL  postgres://…/almi_restore_drill
#   BACKUP_PASSPHRASE_FILE, BACKUP_DIR as for backup.sh
# The target database is dropped and created again. Exit 1 when a table differs.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
: "${SOURCE_URL:?}" "${TARGET_URL:?}"
admin="${TARGET_URL%/*}/postgres"
target="${TARGET_URL##*/}"
psql --no-psqlrc -q --dbname="$admin" -c "DROP DATABASE IF EXISTS \"$target\"" -c "CREATE DATABASE \"$target\""

started=$(date -u +%s)
DATABASE_URL="$SOURCE_URL" "$here/backup.sh"
# Names carry the UTC time, so the last one in sort order is the newest.
dump="$(printf '%s\n' "${BACKUP_DIR:-/var/backups/almi}"/almi-*.dump.gpg | sort | tail -1)"
DATABASE_URL="$TARGET_URL" "$here/restore.sh" "$dump" > /dev/null

status=0
for table in licensing_customer licensing_license licensing_licensekey activation_activation \
  audit_auditevent packages_localserver iam_account; do
  source=$(psql --no-psqlrc -tA --dbname="$SOURCE_URL" -c "SELECT count(*) FROM $table")
  restored=$(psql --no-psqlrc -tA --dbname="$TARGET_URL" -c "SELECT count(*) FROM $table")
  mark=ok; [ "$source" = "$restored" ] || { mark=DIFF; status=1; }
  echo "drill: $mark $table $source/$restored"
done
echo "drill: $(( $(date -u +%s) - started )) s (RTO of stage 1: 4 h)"
exit $status
