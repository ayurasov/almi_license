# /// script
# requires-python = ">=3.13"
# dependencies = ["pynacl==1.6.2", "jsonschema==4.26.0"]
# ///
"""Reference vectors for the server (Python) and the DL module (C++) (E00-04).

Independent of server/ on purpose: PyNaCl only, fixed seeds, deterministic Ed25519.
Writes contracts/vectors/keys, jws and request-signature. Policy vectors are written
by hand (contracts/vectors/policy) and are only format-checked here.

    uv run --script tools/vectors/generate.py           # regenerate
    uv run --script tools/vectors/generate.py --check   # files are up to date and valid
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from nacl.signing import SigningKey
from referencing import Registry
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "contracts" / "vectors"
SCHEMAS = ROOT / "contracts" / "schemas"
SCHEMA_BASE = "https://license.alter-os.ru/schemas/v1/"

NOW = 1762071300  # 2026-11-02T08:15:00Z
DAY = 86400
SEED_LABEL = "almi-license dev vectors v1|"
KEY_NAMES = ("dev-root", "dev-issuer", "dev-local-server", "dev-device")

ROOT_KID = "dev-root"
ISSUER_KID = "dev-issuer-1"
EXPIRED_ISSUER_KID = "dev-issuer-0"
ROGUE_KID = "rogue-1"
SERVER_ID = "srv_01JAB3K9M2N4P6Q8R0S2T4V6W8"
LOCAL_KID = f"{SERVER_ID}-1"
ACTIVATION_ID = "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3"
INSTANCE_ID = "8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c11"
LICENSE_ID = "6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60"
CUSTOMER_ID = "c3a1b2c3-d4e5-4f60-8a9b-0c1d2e3f4a5b"
PRODUCT = "alteroffice-desktop"
STORED_SEQ = 16


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def signing_key(name: str) -> SigningKey:
    return SigningKey(hashlib.sha256((SEED_LABEL + name).encode("ascii")).digest())


def public_b64(key: SigningKey) -> str:
    return b64url(bytes(key.verify_key))


def jwk_thumbprint(key: SigningKey) -> str:
    """RFC 7638 thumbprint of the Ed25519 public key (OKP JWK)."""
    jwk = '{"crv":"Ed25519","kty":"OKP","x":"' + public_b64(key) + '"}'
    return b64url(hashlib.sha256(jwk.encode("ascii")).digest())


def jws(header: dict[str, Any], claims: dict[str, Any], key: SigningKey) -> str:
    signing_input = f"{b64url(canonical(header))}.{b64url(canonical(claims))}"
    signature = key.sign(signing_input.encode("ascii")).signature
    return f"{signing_input}.{b64url(signature)}"


def certificate(
    signer: SigningKey, signer_kid: str, subject: SigningKey, **claims: Any
) -> tuple[str, dict]:
    body = {
        "ver": 1,
        "alg": "EdDSA",
        "pub": public_b64(subject),
        "iss": signer_kid,
    } | claims
    return jws(
        {"alg": "EdDSA", "typ": "alm-cert+jws", "kid": signer_kid}, body, signer
    ), body


def policy() -> dict[str, Any]:
    return {
        "version": 3,
        "enforcement": "enforce",
        "notify_before_days": 30,
        "grace_days": 14,
        "expiry_action": "restrict",
        "restricted_caps": ["updates", "macros", "collaboration"],
        "restricted_days": None,
        "hard_block_mode": "read_only",
        "read_only_caps": ["view", "export", "print"],
        "offline_grace_days": None,
        "check_interval_hours": 24,
        "release_after_days": 30,
    }


def lease_claims(
    keys: dict[str, SigningKey], iss: str, seq: int = 17
) -> dict[str, Any]:
    return {
        "ver": 1,
        "iss": iss,
        "sub": ACTIVATION_ID,
        "aud": PRODUCT,
        "iat": NOW,
        "nbf": NOW,
        "seq": seq,
        "lic": {
            "id": LICENSE_ID,
            "type": "subscription",
            "status": "active",
            "edition": "standard",
            "valid_from": "2026-11-01T00:00:00Z",
            "valid_until": "2027-10-31T20:59:59Z",
            "support_until": "2027-10-31T20:59:59Z",
            "customer": {"id": CUSTOMER_ID, "name": "ООО «Пример»"},
        },
        "subject": {
            "type": "device",
            "instance_id": INSTANCE_ID,
            "fp": {
                "scheme": "fp-v1",
                "components": {
                    "disk": "test-fp-disk",
                    "board": "test-fp-board",
                    "cpu": "test-fp-cpu",
                    "mac": "unknown",
                },
            },
            "device_key_thumbprint": jwk_thumbprint(keys["dev-device"]),
        },
        "limits": {},
        "capabilities": [
            "view",
            "edit",
            "save",
            "create",
            "export",
            "print",
            "updates",
            "support",
        ],
        "policy": policy(),
        "messages": [],
        "server_time": NOW,
    }


def build(keys: dict[str, SigningKey]) -> dict[str, dict[str, Any]]:
    """Return {relative path: document} for every generated file except keys."""
    root, issuer, local, device = (keys[n] for n in KEY_NAMES)
    roots = [{"kid": ROOT_KID, "alg": "EdDSA", "pub": public_b64(root)}]

    issuer_cert, issuer_body = certificate(
        root,
        ROOT_KID,
        issuer,
        kid=ISSUER_KID,
        role="issuer",
        iat=NOW - 30 * DAY,
        nbf=NOW - 30 * DAY,
        exp=NOW + 730 * DAY,
    )
    expired_cert, expired_body = certificate(
        root,
        ROOT_KID,
        issuer,
        kid=EXPIRED_ISSUER_KID,
        role="issuer",
        iat=NOW - 760 * DAY,
        nbf=NOW - 760 * DAY,
        exp=NOW - DAY,
    )
    local_cert, local_body = certificate(
        issuer,
        ISSUER_KID,
        local,
        kid=LOCAL_KID,
        role="local_server",
        iat=NOW - DAY,
        nbf=NOW - DAY,
        exp=NOW + 365 * DAY,
        scope={
            "server_id": SERVER_ID,
            "customer_id": CUSTOMER_ID,
            "products": [PRODUCT],
            "quotas": {LICENSE_ID: 250},
        },
    )

    # A key outside the hierarchy (not saved in keys/): what an attacker certifies with a key
    # that must not sign certificates (section 6.3 of document 2; document 1, §12).
    rogue = signing_key("dev-rogue")
    rogue_issuer_cert, _ = certificate(
        local, LOCAL_KID, rogue, kid=ROGUE_KID, role="issuer",
        iat=NOW - DAY, nbf=NOW - DAY, exp=NOW + 365 * DAY,
    )  # fmt: skip
    rogue_by_issuer_cert, _ = certificate(
        issuer, ISSUER_KID, rogue, kid=ROGUE_KID, role="issuer",
        iat=NOW - DAY, nbf=NOW - DAY, exp=NOW + 365 * DAY,
    )  # fmt: skip
    shadow_root_cert, _ = certificate(
        issuer, ISSUER_KID, rogue, kid=ROOT_KID, role="local_server",
        iat=NOW - DAY, nbf=NOW - DAY, exp=NOW + 365 * DAY,
        scope={"server_id": SERVER_ID, "customer_id": CUSTOMER_ID, "products": [PRODUCT],
               "quotas": {LICENSE_ID: 1}},
    )  # fmt: skip

    def lease_header(
        kid: str, chain: list[str], typ: str = "alm-lease+jws", alg: str = "EdDSA"
    ) -> dict:
        return {"alg": alg, "typ": typ, "kid": kid, "chain": chain}

    central = lease_claims(keys, "https://license.alter-os.ru")
    local_lease = lease_claims(keys, f"urn:almi:ls:{SERVER_ID}")
    valid = jws(lease_header(ISSUER_KID, [issuer_cert]), central, issuer)
    head, payload, sig = valid.split(".")

    def vector(
        name: str,
        description: str,
        token: str,
        error: str | None,
        *,
        claims: dict | None = None,
        stored_seq: int = STORED_SEQ,
        revoked: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "jws": token,
            "trust_roots": roots,
            "now": NOW,
            "context": {
                "product_code": PRODUCT,
                "instance_id": INSTANCE_ID,
                "device_key_thumbprint": jwk_thumbprint(device),
                "stored_seq": stored_seq,
                "revoked_kids": revoked or [],
            },
            "expected": {"valid": error is None, "error": error, "claims": claims},
        }

    tampered = dict(central, seq=99)
    padded_signature = b64url(base64.urlsafe_b64decode(sig + "==") + b"\x00")
    vectors = [
        vector(
            "01-valid-lease",
            "Аренда центрального сервера: ключ выпуска, сертификат от корня.",
            valid,
            None,
            claims=central,
        ),
        vector(
            "02-valid-local-server-lease",
            "Аренда локального сервера: корень → ключ выпуска → ключ локального сервера (3 звена).",
            jws(lease_header(LOCAL_KID, [local_cert, issuer_cert]), local_lease, local),
            None,
            claims=local_lease,
        ),
        vector(
            "03-foreign-signature",
            "Подписано ключом устройства вместо ключа выпуска из заголовка.",
            jws(lease_header(ISSUER_KID, [issuer_cert]), central, device),
            "signature_invalid",
        ),
        vector(
            "04-tampered-payload",
            "Полезная нагрузка изменена после подписи (seq 17 → 99).",
            f"{head}.{b64url(canonical(tampered))}.{sig}",
            "signature_invalid",
        ),
        vector(
            "05-revoked-kid",
            "kid ключа выпуска в списке отзыва.",
            valid,
            "kid_revoked",
            revoked=[ISSUER_KID],
        ),
        vector(
            "06-expired-issuer-certificate",
            "Сертификат ключа выпуска истёк за сутки до now.",
            jws(lease_header(EXPIRED_ISSUER_KID, [expired_cert]), central, issuer),
            "cert_expired",
        ),
        vector(
            "07-seq-lower",
            "seq аренды (17) меньше применённого (20).",
            valid,
            "seq_not_greater",
            stored_seq=20,
        ),
        vector(
            "08-seq-equal",
            "seq аренды (17) равен применённому (17).",
            valid,
            "seq_not_greater",
            stored_seq=17,
        ),
        vector(
            "09-unknown-alg",
            "alg ES256 не поддерживается (подпись при этом Ed25519).",
            jws(lease_header(ISSUER_KID, [issuer_cert], alg="ES256"), central, issuer),
            "alg_unsupported",
        ),
        vector(
            "10-alg-none",
            "alg none и пустая подпись.",
            f"{b64url(canonical(lease_header(ISSUER_KID, [issuer_cert], alg='none')))}.{payload}.",
            "alg_unsupported",
        ),
        vector(
            "11-wrong-typ",
            "typ alm-package+jws вместо alm-lease+jws, подпись верна.",
            jws(
                lease_header(ISSUER_KID, [issuer_cert], typ="alm-package+jws"),
                central,
                issuer,
            ),
            "typ_invalid",
        ),
        vector(
            "12-extra-bytes-in-base64url",
            "К подписи дописан лишний байт: 65 байт вместо 64.",
            f"{head}.{payload}.{padded_signature}",
            "malformed",
        ),
        vector(
            "13-local-server-issues-issuer",
            "Ключ локального сервера выпустил себе сертификат issuer и подписал им аренду: "
            "сертификаты подписывают только корень и issuer.",
            jws(
                lease_header(ROGUE_KID, [rogue_issuer_cert, local_cert, issuer_cert]),
                central,
                rogue,
            ),
            "chain_invalid",
        ),
        vector(
            "14-issuer-issues-issuer",
            "Ключ выпуска выпустил сертификат issuer: issuer подписывает только local_server.",
            jws(lease_header(ROGUE_KID, [rogue_by_issuer_cert, issuer_cert]), central, rogue),
            "chain_invalid",
        ),
        vector(
            "15-certificate-replaces-root-kid",
            "Сертификат от ключа выпуска с kid корня подменил бы ключ корня в цепочке.",
            jws(lease_header(ROOT_KID, [shadow_root_cert, issuer_cert]), central, rogue),
            "chain_invalid",
        ),
    ]

    files: dict[str, dict[str, Any]] = {f"jws/{v['name']}.json": v for v in vectors}
    files.update(request_signature_vectors(device))
    files["_claims"] = {
        "lease": [central, local_lease],
        "cert": [issuer_body, expired_body, local_body],
    }
    return files


def signing_string(
    method: str, path: str, created: int, nonce: str, body: bytes
) -> tuple[str, str]:
    body_hash = b64url(hashlib.sha256(body).digest())
    return "\n".join(
        ["ALMI-REQ-V1", method.upper(), path, str(created), nonce, body_hash]
    ), body_hash


def request_signature_vectors(device: SigningKey) -> dict[str, dict[str, Any]]:
    nonce = b64url(hashlib.sha256(b"almi-license vectors nonce").digest()[:16])
    short_nonce = b64url(
        hashlib.sha256(b"almi-license vectors short nonce").digest()[:8]
    )
    check_path = f"/api/v1/activations/{ACTIVATION_ID}/check"
    check_body = canonical(
        {"lease_seq": 17, "state": "ACTIVE", "client_time": "2026-11-02T08:14:58Z"}
    ).decode()
    events_body = canonical(
        {
            "activation_id": ACTIVATION_ID,
            "events": [
                {
                    "id": "evt_01",
                    "type": "feature_denied",
                    "at": "2026-11-02T08:14:58Z",
                    "data": {
                        "feature": "macros",
                        "comment": "Макросы — «недоступны» ✓",
                    },
                }
            ],
        }
    ).decode()

    cases = [
        (
            "01-get-without-body",
            "GET с query-строкой, пустое тело.",
            "GET",
            "/api/v1/trust?since_seq=3",
            "",
            nonce,
            NOW,
            None,
            None,
        ),
        (
            "02-post-with-body",
            "POST проверки с JSON-телом.",
            "POST",
            check_path,
            check_body,
            nonce,
            NOW,
            None,
            None,
        ),
        (
            "03-unicode-body",
            "Тело с кириллицей и символами вне ASCII; хэш считается по байтам UTF-8.",
            "POST",
            "/api/v1/events",
            events_body,
            nonce,
            NOW,
            None,
            None,
        ),
        (
            "04-invalid-nonce",
            "nonce — 8 байт вместо 16.",
            "POST",
            check_path,
            check_body,
            short_nonce,
            NOW,
            "signature_invalid",
            None,
        ),
        (
            "05-expired-created",
            "created на 301 с раньше времени сервера (допуск 300 с).",
            "POST",
            check_path,
            check_body,
            nonce,
            NOW - 301,
            "clock_skew",
            None,
        ),
        (
            "06-changed-path",
            "Подписан путь …/check, запрос отправлен на …/release.",
            "POST",
            check_path,
            check_body,
            nonce,
            NOW,
            "signature_invalid",
            f"/api/v1/activations/{ACTIVATION_ID}/release",
        ),
    ]
    files = {}
    for (
        name,
        description,
        method,
        path,
        body,
        case_nonce,
        created,
        error,
        sent_path,
    ) in cases:
        string, body_hash = signing_string(
            method, path, created, case_nonce, body.encode("utf-8")
        )
        signature = b64url(device.sign(string.encode("utf-8")).signature)
        header = f'keyid="{ACTIVATION_ID}", alg="ed25519", created={created}, nonce="{case_nonce}", sig="{signature}"'
        files[f"request-signature/{name}.json"] = {
            "name": name,
            "description": description,
            "public_key": public_b64(device),
            "server_now": NOW,
            "request": {"method": method, "path": sent_path or path, "body": body},
            "signed": {
                "keyid": ACTIVATION_ID,
                "alg": "ed25519",
                "created": created,
                "nonce": case_nonce,
                "path": path,
            },
            "expected": {
                "body_sha256": body_hash,
                "signing_string": string,
                "signature": signature,
                "header": header,
                "valid": error is None,
                "error": error,
            },
        }
    return files


def render(keys: dict[str, SigningKey]) -> dict[str, str]:
    files = {
        f"keys/{name}.key": b64url(bytes(key)) + "\n" for name, key in keys.items()
    }
    files |= {f"keys/{name}.pub": public_b64(key) + "\n" for name, key in keys.items()}
    files |= {
        path: pretty(doc)
        for path, doc in build(keys).items()
        if not path.startswith("_")
    }
    return files


def schema_validator(name: str) -> Draft202012Validator:
    registry = Registry().with_resources(
        (doc["$id"], DRAFT202012.create_resource(doc))
        for doc in (
            json.loads(p.read_text(encoding="utf-8"))
            for p in SCHEMAS.glob("*.schema.json")
        )
    )
    return Draft202012Validator(
        {"$ref": f"{SCHEMA_BASE}{name}.schema.json"}, registry=registry
    )


def check(keys: dict[str, SigningKey]) -> list[str]:
    problems = []
    for path, content in render(keys).items():
        target = VECTORS / path
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            problems.append(
                f"{path}: differs from the generator output (run generate.py)"
            )
    claims = build(keys)["_claims"]
    for kind, docs in claims.items():
        validator = schema_validator(kind)
        for doc in docs:
            problems += [
                f"{kind} claims: {e.message}" for e in validator.iter_errors(doc)
            ]
    policy_validator = schema_validator("policy")
    policy_files = sorted((VECTORS / "policy").glob("*.json"))
    for path in policy_files:
        vector = json.loads(path.read_text(encoding="utf-8"))
        missing = {
            "name",
            "reasoning",
            "policy",
            "license",
            "now",
            "last_success_at",
            "expected",
        } - vector.keys()
        if missing:
            problems.append(f"policy/{path.name}: missing {sorted(missing)}")
            continue
        problems += [
            f"policy/{path.name}: policy {e.message}"
            for e in policy_validator.iter_errors(vector["policy"])
        ]
        if vector["name"] != path.stem:
            problems.append(f"policy/{path.name}: name must match the file name")
    if len(policy_files) < 36:
        problems.append(f"policy: {len(policy_files)} vectors, at least 36 required")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="verify instead of writing"
    )
    args = parser.parse_args()
    keys = {name: signing_key(name) for name in KEY_NAMES}
    if args.check:
        problems = check(keys)
        for problem in problems:
            print(f"  - {problem}")
        print("vectors: OK" if not problems else f"vectors: {len(problems)} problem(s)")
        return 1 if problems else 0
    for path, content in render(keys).items():
        target = VECTORS / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"written {len(render(keys))} files to {VECTORS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
