#!/usr/bin/env bash
# State of the installed local server (E15-04): services, API, package term, free space.
# Exit 1 when something needs attention; the output names it.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
status=0
ok() { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; status=1; }
warn() { printf 'warn  %s\n' "$*"; }

for service in db api worker console gateway; do
  state="$(docker compose ps --format '{{.State}}' "$service" 2> /dev/null | head -1)"
  if [[ "$state" == "running" ]]; then ok "service $service"; else bad "service $service is ${state:-absent}"; fi
done

if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=5)" > /dev/null 2>&1; then
  ok "API ready"
else
  bad "API is not ready (docker compose logs api)"
fi

# Registration, package term and usage reports, printed by the server itself.
if ! docker compose exec -T api almi-entrypoint manage local_status --check; then
  bad "the local server needs attention (see above)"
fi

# Thresholds of the disk in percent used (CHECK_DISK_WARN, CHECK_DISK_FAIL).
warn_at="${CHECK_DISK_WARN:-80}"
fail_at="${CHECK_DISK_FAIL:-90}"
used="$(df --output=pcent . | tail -1 | tr -dc '0-9')"
if [[ "$used" -ge "$fail_at" ]]; then bad "disk is ${used} % full"; elif [[ "$used" -ge "$warn_at" ]]; then warn "disk is ${used} % full"; else ok "disk ${used} % used"; fi
if [[ -f backups/last-success ]]; then
  age=$(( $(date -u +%s) - $(< backups/last-success) ))
  if (( age < 93600 )); then ok "last backup $(( age / 3600 )) h ago"; else warn "last backup is older than 26 h"; fi
else
  warn "no backup yet (./backup.sh, cron: docs/install.md)"
fi
exit $status
