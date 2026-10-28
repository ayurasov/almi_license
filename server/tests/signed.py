"""Signed Product API requests for tests: ALMI-Signature with an Ed25519 device key."""

import json
import secrets
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client

from infra.clock import current_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from infra.request_signing import signing_string
from tests.vectors import key_path


def dev_device_key() -> Ed25519PrivateKey:
    seed = b64url_decode(key_path("dev-device.key").read_text(encoding="ascii").strip())
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_b64(key: Ed25519PrivateKey) -> str:
    return b64url_encode(key.public_key().public_bytes_raw())


def signed_post(
    client: Client,
    path: str,
    document: dict[str, Any],
    key: Ed25519PrivateKey,
    keyid: str,
    headers: dict[str, str] | None = None,
) -> Any:
    body = json.dumps(document, ensure_ascii=False).encode("utf-8")
    created = int(current_clock().now().timestamp())
    nonce = b64url_encode(secrets.token_bytes(16))
    sig = b64url_encode(key.sign(signing_string("POST", path, created, nonce, body)))
    header = f'keyid="{keyid}", alg="ed25519", created={created}, nonce="{nonce}", sig="{sig}"'
    return client.generic(
        "POST",
        path,
        body,
        content_type="application/json",
        HTTP_ALMI_SIGNATURE=header,
        headers=headers or {},
    )
