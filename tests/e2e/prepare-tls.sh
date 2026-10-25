#!/usr/bin/env bash
# Certificates of the end-to-end stand (E16-04): a CA of this run and a server certificate for
# localhost; the CA goes into the system trust store, so the DL module checks TLS as in production.
#   tests/e2e/prepare-tls.sh DIR      (root, or sudo for the trust store)
set -euo pipefail
dir="${1:?usage: prepare-tls.sh DIR}"
mkdir -p "$dir"
cd "$dir"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 400 \
  -subj "/CN=ALMI e2e stand CA" -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" -keyout ca.key -out ca.crt 2> /dev/null
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=localhost" \
  -keyout server.key -out server.csr 2> /dev/null
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature\nauthorityKeyIdentifier=keyid\n' > ext.cnf
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 400 \
  -extfile ext.cnf -out server.crt 2> /dev/null
rm -f ca.key server.csr ext.cnf
sudo_() { if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi; }
sudo_ cp ca.crt /usr/local/share/ca-certificates/almi-e2e-stand.crt
sudo_ update-ca-certificates > /dev/null
echo "stand TLS in $dir"
