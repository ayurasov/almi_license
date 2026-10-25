"""Signed requests of the load scenarios (E16-05): run with the Python of the server.

    PYTHONPATH=server server/.venv/bin/python tests/load/sign.py STAND.json OUT_DIR \
        --start UNIX --check-rate 100 --check-seconds 900 --activate-rate 20 --activate-seconds 600

A request is signed by its device key (section 4.4 of document 2) with created = the second it is
due in the run, so the whole run stays within the 300 s tolerance of the server. Every request has
its own nonce. STAND.json comes from manage.py seed_load (private keys: a stand only).
"""

import argparse
import json
import secrets
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from infra.crypto.encoding import b64url_decode, b64url_encode
from infra.request_signing import signature_header, signing_string

OS = {"family": "windows", "name": "Windows 11 Pro", "version": "10.0", "arch": "x86_64"}
FP = {"scheme": "fp-v1", "components": {"disk": "d", "board": "b", "cpu": "c", "mac": "m"}}


def _rfc3339(unix: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(unix, UTC).isoformat().replace("+00:00", "Z")


def signed(
    key: Ed25519PrivateKey, keyid: str, path: str, document: dict[str, Any], created: int
) -> dict[str, str]:
    body = json.dumps(document, separators=(",", ":")).encode()
    nonce = b64url_encode(secrets.token_bytes(16))
    sig = b64url_encode(key.sign(signing_string("POST", path, created, nonce, body)))
    return {
        "path": path,
        "body": body.decode(),
        "signature": signature_header(keyid, created, nonce, sig),
    }


def check_request(signer: dict[str, str], created: int) -> dict[str, str]:
    key = Ed25519PrivateKey.from_private_bytes(b64url_decode(signer["seed"]))
    document = {
        "lease_seq": 1,
        "product": {"code": "alteroffice-desktop", "version": "3.2.0"},
        "instance": {"os": OS},
        "fingerprint": FP,
        "state": "ACTIVE",
        "client_time": _rfc3339(created),
    }
    path = f"/api/v1/activations/{signer['activation_id']}/check"
    return signed(key, signer["activation_id"], path, document, created)


def activate_request(license_key: str, created: int) -> dict[str, str]:
    key = Ed25519PrivateKey.generate()
    document = {
        "license_key": license_key,
        "product": {"code": "alteroffice-desktop", "version": "3.2.0"},
        "instance": {
            "instance_id": str(uuid.uuid4()),
            "subject_type": "device",
            "name": "WS-LOAD",
            "os": OS,
        },
        "fingerprint": FP,
        "device_pubkey": b64url_encode(key.public_key().public_bytes_raw()),
        "client_time": _rfc3339(created),
    }
    return signed(key, "device", "/api/v1/activations", document, created)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stand", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--start", type=int, required=True, help="unix time the run starts")
    parser.add_argument("--check-rate", type=int, default=100)
    parser.add_argument("--check-seconds", type=int, default=900)
    parser.add_argument("--activate-rate", type=int, default=20)
    parser.add_argument("--activate-seconds", type=int, default=600)
    parser.add_argument("--race", type=int, default=200, help="activations of the hot licence")
    args = parser.parse_args()
    stand = json.loads(args.stand.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    signers = stand["signers"]
    # One second more than the run: k6 may start one iteration past rate * duration, and a
    # request is never sent twice (its nonce is used up).
    total = args.check_rate * (args.check_seconds + 1)
    checks = [
        check_request(signers[i % len(signers)], args.start + i // args.check_rate)
        for i in range(total)
    ]
    # The activation scenario starts after the check scenario (run.sh runs them one by one).
    begin = args.start + args.check_seconds
    total = args.activate_rate * (args.activate_seconds + 1)
    spare = stand["spare"]
    activations = [
        activate_request(spare[i % len(spare)], begin + i // args.activate_rate)
        for i in range(total)
    ]
    race_at = begin + args.activate_seconds
    race = [activate_request(stand["hot"]["key"], race_at) for _ in range(args.race)]
    for name, requests in (("check", checks), ("activate", activations), ("race", race)):
        target = args.out / f"{name}.json"
        target.write_text(json.dumps(requests), encoding="utf-8")
        target.chmod(0o600)
    print(
        f"{len(checks)} check, {len(activations)} activate, {len(race)} race requests in {args.out}"
    )


if __name__ == "__main__":
    main()
