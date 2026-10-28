#!/usr/bin/env bash
# Entry points of the server image (docs/specs/07-environments.md, section 7.1):
#   api      Gunicorn with Uvicorn workers on :8000 (WEB_CONCURRENCY, default 2)
#   worker   task queue and schedule (E12-01)
#   migrate  database migrations, before api and worker start; as the owner of the tables, then
#            the rights of APP_DATABASE_ROLE (the role of api and worker, question 38)
#   manage   any manage.py command
# Secrets come from Docker secret files: DATABASE_PASSWORD_FILE completes DATABASE_URL
# (postgres://USER@HOST:PORT/NAME without a password), DJANGO_SECRET_KEY_FILE sets the key.
set -euo pipefail

if [[ -n "${DATABASE_PASSWORD_FILE:-}" ]]; then
  password="$(python -c 'import sys, urllib.parse; print(urllib.parse.quote(open(sys.argv[1]).read().strip(), safe=""))' "$DATABASE_PASSWORD_FILE")"
  DATABASE_URL="${DATABASE_URL/@/:${password}@}"
  export DATABASE_URL
fi
if [[ -n "${DJANGO_SECRET_KEY_FILE:-}" ]]; then
  DJANGO_SECRET_KEY="$(< "$DJANGO_SECRET_KEY_FILE")"
  export DJANGO_SECRET_KEY
fi

command="${1:-api}"
shift || true
case "$command" in
  api)
    # Metrics of all worker processes are added up from this directory (question 42); values of
    # the previous start are dropped.
    export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/almi-metrics}"
    rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    exec gunicorn almi_license.asgi:application --worker-class uvicorn_worker.UvicornWorker \
      --config python:almi_license.gunicorn_conf \
      --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-2}" --access-logfile - --forwarded-allow-ips '*' "$@"
    ;;
  worker) exec python manage.py run_worker "$@" ;;
  migrate)
    python manage.py migrate --noinput "$@"
    if [[ -n "${APP_DATABASE_ROLE:-}" ]]; then
      exec python manage.py grant_app_role "$APP_DATABASE_ROLE" ${APP_DATABASE_PASSWORD_FILE:+--password-file "$APP_DATABASE_PASSWORD_FILE"}
    fi
    ;;
  manage) exec python manage.py "$@" ;;
  *) echo "unknown command $command: api, worker, migrate or manage" >&2; exit 2 ;;
esac
