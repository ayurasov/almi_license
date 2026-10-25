#!/usr/bin/env bash
# A load stand on this host (E16-05): a fresh database next to DATABASE_URL, the API under uvicorn
# with 2 workers and the connection pool, rate limits off; then run.sh; then the server stops.
#   SMOKE=1 tests/load/stand.sh OUT_DIR      (make load-smoke, CI)
set -euo pipefail
out="${1:?usage: stand.sh OUT_DIR}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
: "${DATABASE_URL:?}"
base="${DATABASE_URL%/*}"
export DATABASE_URL="$base/almi_load"
psql "$base/postgres" -qc "DROP DATABASE IF EXISTS almi_load WITH (FORCE)" -c "CREATE DATABASE almi_load"
export DJANGO_SETTINGS_MODULE=almi_license.settings.dev DEPLOYMENT_MODE=central
export SIGNING_KEY_FILE="$repo/contracts/vectors/keys/dev-issuer.key" SIGNING_CERT_FILE="$repo/deploy/dev/dev-issuer-1.cert.jws"
export RATE_LIMIT_ACTIVATE_IP=0 RATE_LIMIT_ACTIVATE_KEY=0 RATE_LIMIT_CHECK_IP=0 RATE_LIMIT_CHECK_ACTIVATION=0
export DATABASE_POOL_MAX_SIZE="${DATABASE_POOL_MAX_SIZE:-20}" BASE_URL="http://127.0.0.1:${LOAD_PORT:-8090}"
cd "$repo/server"
.venv/bin/python manage.py migrate -v0
.venv/bin/python manage.py loadcatalog -v0 > /dev/null
mkdir -p "$out"
.venv/bin/python -m uvicorn almi_license.asgi:application --host 127.0.0.1 --port "${LOAD_PORT:-8090}" \
  --workers "${LOAD_WORKERS:-2}" --log-level warning > "$out/server.log" 2>&1 &
server=$!
trap 'kill $server 2> /dev/null || true' EXIT
for _ in $(seq 60); do curl -fsS "$BASE_URL/health" > /dev/null 2>&1 && break; sleep 1; done
"$repo/tests/load/run.sh" "$out"
