#!/usr/bin/env bash
# Install the local server from this bundle on a host without internet (E15-04).
#   ./install.sh            load the images, create secrets and TLS, start, check
# Needs Docker 24+ with the compose plugin. Run from the unpacked bundle directory.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '[install] %s\n' "$*"; }
fail() { printf '[install] error: %s\n' "$*" >&2; exit 1; }

command -v docker > /dev/null || fail "Docker is not installed"
major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
[[ "$major" -ge 24 ]] || fail "Docker 24 or newer is required (found $major)"
docker compose version > /dev/null || fail "the docker compose plugin is required"

say "checking SHA256SUMS"
sha256sum --check --quiet SHA256SUMS || fail "the bundle is damaged: SHA256SUMS does not match"
if [[ -f SHA256SUMS.sig ]]; then
  say "SHA256SUMS.sig present: verify it with almi-keytool on a trusted machine (docs/install.md)"
fi

say "loading images"
for image in images/*.tar; do docker load --quiet --input "$image" > /dev/null; done

[[ -f .env ]] || cp .env.example .env
# shellcheck disable=SC1091
source .env
[[ -n "${TRUST_ROOTS:-}" ]] || fail "TRUST_ROOTS is empty in .env"
[[ "$SERVER_NAME" != "license.example.local" ]] || say "SERVER_NAME is the example value; set it in .env"

umask 077
mkdir -p secrets tls backups
new_secret() { [[ -s "secrets/$1" ]] || openssl rand -hex 32 > "secrets/$1"; }
new_secret db_password
new_secret app_db_password
new_secret django_secret
new_secret backup_passphrase
[[ -s secrets/db_url ]] || printf 'postgres://almi:%s@db:5432/almi_local\n' "$(< secrets/db_password)" > secrets/db_url
# The containers run as other users and read the secrets through Docker: the files are 0644,
# the secrets directory itself stays 0700 (umask above).
chmod 644 secrets/*

if [[ ! -s tls/server.crt ]]; then
  say "no tls/server.crt: creating a self-signed certificate for $SERVER_NAME (replace it with the certificate of the customer CA)"
  openssl req -x509 -newkey rsa:3072 -nodes -days 825 -subj "/CN=$SERVER_NAME" \
    -addext "subjectAltName=DNS:$SERVER_NAME" -keyout tls/server.key -out tls/server.crt 2> /dev/null
  chmod 644 tls/server.crt tls/server.key
fi

say "starting"
docker compose up -d --wait --wait-timeout 600
./check.sh
say "done: open https://$SERVER_NAME:$HTTPS_PORT/ and run the first-run wizard"
