#!/usr/bin/env bash
# State of the central server: services, API, discovery document, disk, last backup.
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
# shellcheck disable=SC1091
source .env
if curl -fsSk --max-time 5 "https://localhost:${HTTPS_PORT:-443}/.well-known/almi-license" > /dev/null; then
  ok "gateway answers on https://localhost:${HTTPS_PORT:-443}"
else
  bad "the gateway does not answer (docker compose logs gateway)"
fi
if curl -fsSk --max-time 5 "https://localhost:${HTTPS_PORT:-443}/api/v1/trust" > /dev/null; then
  ok "trust bundle served"
else
  warn "no trust bundle: put trust.json of almi-keytool export-trust into ./trust (docs/deployment.md)"
fi
used="$(df --output=pcent . | tail -1 | tr -dc '0-9')"
if [[ "$used" -ge "${CHECK_DISK_FAIL:-90}" ]]; then bad "disk is ${used} % full"; elif [[ "$used" -ge "${CHECK_DISK_WARN:-80}" ]]; then warn "disk is ${used} % full"; else ok "disk ${used} % used"; fi
if [[ -f backups/last-success ]]; then
  age=$(( $(date -u +%s) - $(< backups/last-success) ))
  if (( age < 93600 )); then ok "last backup $(( age / 3600 )) h ago"; else warn "last backup is older than 26 h"; fi
else
  warn "no backup yet (./backup.sh; cron: docs/deployment.md)"
fi
exit $status
