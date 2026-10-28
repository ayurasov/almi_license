#!/usr/bin/env bash
# Upgrade to the images of a new bundle (E15-04, E15-06): ./upgrade.sh /path/to/new-bundle
# A backup first and the files of the current version in ./previous; a failed migration rolls
# back by itself (rollback.sh: previous files, previous images, the backup of this upgrade).
set -euo pipefail
cd "$(dirname "$0")"
new="${1:?usage: upgrade.sh <unpacked new bundle>}"
(cd "$new" && sha256sum --check --quiet SHA256SUMS) || { echo "[upgrade] the new bundle is damaged" >&2; exit 1; }
# shellcheck disable=SC1091
source .env
previous="$ALMI_VERSION"
next="$(sed -n 's/^ALMI_VERSION=//p' "$new/.env.example")"
echo "[upgrade] $previous -> $next: backup"
./backup.sh
copies=(backups/almi-*.dump.gpg)  # named by UTC time: the last one is the newest
backup="${copies[-1]}"
rm -rf previous && mkdir previous
cp docker-compose.yml gateway.conf.template install.sh upgrade.sh check.sh backup.sh restore.sh .env previous/
[[ -f rollback.sh ]] && cp rollback.sh previous/
cp -r ops previous/
printf '%s\n' "$backup" > previous/backup
for image in "$new"/images/*.tar; do docker load --quiet --input "$image" > /dev/null; done
cp "$new"/{docker-compose.yml,gateway.conf.template,install.sh,upgrade.sh,rollback.sh,check.sh,backup.sh,restore.sh} .
cp -r "$new"/ops .
sed -i "s/^ALMI_VERSION=.*/ALMI_VERSION=$next/" .env
# Bundles before v0.4.2 have no application role (question 38): its password is created here.
if [[ ! -s secrets/app_db_password ]]; then
  (umask 077 && openssl rand -hex 32 > secrets/app_db_password)
  chmod 644 secrets/app_db_password
fi
if ! docker compose run --rm migrate; then
  echo "[upgrade] migration failed: back to $previous" >&2
  ./rollback.sh
  exit 1
fi
docker compose up -d --wait
./check.sh
echo "[upgrade] done; ./rollback.sh returns to $previous with the data of $backup"
