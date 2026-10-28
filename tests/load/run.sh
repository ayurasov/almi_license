#!/usr/bin/env bash
# Load run of stage 1 (E16-05): seed-load, signed requests, k6 check / activate / race, the race
# result, /metrics and the top-10 queries of pg_stat_statements; a Markdown report.
#   tests/load/run.sh OUT_DIR            full targets (a load stand: staging-like hardware)
#   SMOKE=1 tests/load/run.sh OUT_DIR    the same steps in a minute (CI)
# Needs: DATABASE_URL of the stand database, BASE_URL of its API (rate limits off), docker (k6),
# psql. The server must run with SEED_LOAD_ALLOWED=1 for manage.py seed_load.
set -euo pipefail
out="${1:?usage: run.sh OUT_DIR}"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
: "${DATABASE_URL:?}" "${BASE_URL:?}"
K6_IMAGE="${K6_IMAGE:-grafana/k6:2.3.0}"
mkdir -p "$out"
umask 077

if [[ "${SMOKE:-0}" == "1" ]]; then
  licenses=100 activations=2000 signers=500 check_rate=20 check_s=20 act_rate=5 act_s=20 race=200
else
  licenses=20000 activations=500000 signers=10000 check_rate=100 check_s=900 act_rate=20 act_s=600 race=200
fi

manage() { (cd "$repo/server" && SEED_LOAD_ALLOWED=1 .venv/bin/python manage.py "$@"); }
echo "[load] seed-load: $licenses licences, $activations activations"
manage seed_load --licenses "$licenses" --activations "$activations" --signers "$signers" --out "$out/stand.json"

start=$(( $(date +%s) + 30 ))
echo "[load] signing requests"
PYTHONPATH="$repo/server" "$repo/server/.venv/bin/python" "$repo/tests/load/sign.py" "$out/stand.json" "$out" \
  --start "$start" --check-rate "$check_rate" --check-seconds "$check_s" \
  --activate-rate "$act_rate" --activate-seconds "$act_s" --race "$race"
psql "$DATABASE_URL" -qc "SELECT pg_stat_statements_reset()" > /dev/null 2>&1 || echo "[load] pg_stat_statements is not enabled"
while (( $(date +%s) < start )); do sleep 1; done

k6() {
  docker run --rm --network host -u "$(id -u):$(id -g)" -v "$repo/tests/load:/scripts:ro" -v "$out:/out" "$K6_IMAGE" \
    run --quiet --summary-export "/out/$1-summary.json" -e SCENARIO="$1" -e BASE_URL="$BASE_URL" \
    -e REQUESTS="/out/$1.json" -e RATE="$2" -e SECONDS="$3" -e RACE="$race" /scripts/scenario.js
}
status=0
k6 check "$check_rate" "$check_s" || status=1
k6 activate "$act_rate" "$act_s" || status=1
k6 race 0 0 || status=1

hot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hot"]["license_id"])' "$out/stand.json")"
active="$(psql "$DATABASE_URL" -Atc "SELECT count(*) FROM activation_activation WHERE license_id = '$hot' AND status = 'active'")"
expected=103  # limit 100 + reserve ceil(100 * 3 %)
echo "[load] race: $active active activations of the hot licence (expected $expected)"
[[ "$active" == "$expected" ]] || status=1
curl -fsS "$BASE_URL/metrics" > "$out/metrics.txt" || true
psql "$DATABASE_URL" -f "$repo/tests/load/top-queries.sql" > "$out/top-queries.txt" 2>&1 || true

python3 "$repo/tests/load/report.py" "$out" "$active" "$expected" > "$out/report.md"
rm -f "$out/stand.json" "$out"/check.json "$out"/activate.json "$out"/race.json  # private keys
echo "[load] report: $out/report.md"
exit "$status"
