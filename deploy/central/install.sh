#!/usr/bin/env bash
# Install the central server on this host from a checkout of the repository (docs/deployment.md).
#   ./install.sh                 keys/issuer.key and keys/issuer.cert.jws from the key ceremony
#   DEV_ISSUER=1 ./install.sh    a trial server with the public dev keys of the repository
#   ADMIN_USER=name ./install.sh also the first administrator; the password is asked without echo
#                                (or taken from CONSOLE_PASSWORD), never an argument
# Builds the images, creates secrets and a TLS certificate if absent, starts, loads the catalogue.
set -euo pipefail
cd "$(dirname "$0")"
repo="$(cd ../.. && pwd)"
say() { printf '[install] %s\n' "$*"; }
fail() { printf '[install] error: %s\n' "$*" >&2; exit 1; }

command -v docker > /dev/null || fail "Docker is not installed (docs/deployment.md, step 1)"
docker compose version > /dev/null || fail "the docker compose plugin is required"
[[ -f .env ]] || cp .env.example .env
# shellcheck disable=SC1091
source .env
[[ "$SERVER_NAME" != "license.example.ru" ]] || say "SERVER_NAME is the example value; set it in .env"

umask 077
mkdir -p secrets tls backups keys
new_secret() { [[ -s "secrets/$1" ]] || openssl rand -hex 32 > "secrets/$1"; }
new_secret db_password
new_secret app_db_password
new_secret django_secret
new_secret backup_passphrase
[[ -s secrets/db_url ]] || printf 'postgres://almi:%s@db:5432/almi_license\n' "$(< secrets/db_password)" > secrets/db_url

if [[ ! -s keys/issuer.key ]]; then
  if [[ "${DEV_ISSUER:-0}" == "1" ]]; then
    say "DEV_ISSUER=1: the public dev issuer of the repository — a TRIAL server only"
    cp "$repo/contracts/vectors/keys/dev-issuer.key" keys/issuer.key
    cp "$repo/deploy/dev/dev-issuer-1.cert.jws" keys/issuer.cert.jws
    root="$(tr -d '\n' < "$repo/contracts/vectors/keys/dev-root.pub")"
    grep -q '^TRUST_ROOTS=.\+' .env || sed -i "s|^TRUST_ROOTS=.*|TRUST_ROOTS=dev-root:$root|" .env
  else
    fail "no keys/issuer.key: put the issuer key and certificate of the key ceremony there (or DEV_ISSUER=1)"
  fi
fi
# The containers read the secrets as another user: the files are 0644 inside a 0700 directory.
chmod 644 secrets/* keys/*

if [[ ! -s tls/server.crt ]]; then
  say "no tls/server.crt: a self-signed certificate for $SERVER_NAME (replace it, docs/deployment.md)"
  openssl req -x509 -newkey rsa:3072 -nodes -days 825 -subj "/CN=$SERVER_NAME" \
    -addext "subjectAltName=DNS:$SERVER_NAME" -keyout tls/server.key -out tls/server.crt 2> /dev/null
  chmod 644 tls/server.crt tls/server.key
fi

say "building images $ALMI_VERSION"
docker build -q -f "$repo/deploy/Dockerfile" --target runtime --build-arg APP_VERSION="$ALMI_VERSION" \
  -t "almi-license:$ALMI_VERSION" "$repo" > /dev/null
docker build -q -f "$repo/deploy/console/Dockerfile" -t "almi-license-console:$ALMI_VERSION" "$repo" > /dev/null

say "starting"
docker compose up -d --wait --wait-timeout 600
docker compose run --rm api manage loadcatalog
if [[ -n "${ADMIN_USER:-}" ]]; then
  docker compose run --rm ${CONSOLE_PASSWORD:+-e CONSOLE_PASSWORD} api manage create_account \
    --username "$ADMIN_USER" --role admin
fi
./check.sh
say "done: open https://$SERVER_NAME/ (first administrator: docs/deployment.md, step 7)"
