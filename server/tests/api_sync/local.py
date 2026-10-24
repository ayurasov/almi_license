"""A local server for Sync API tests: its own Ed25519 key and signed requests."""

import json
import secrets
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client

from infra.clock import current_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from infra.ids import new_ulid
from infra.request_signing import signing_string

REGISTER = "/api/sync/v1/servers/register"


class LocalServerClient:
    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        self.server_id = f"srv_{new_ulid(current_clock().now())}"
        self.client = Client()

    @property
    def public_key(self) -> str:
        return b64url_encode(self.key.public_key().public_bytes_raw())

    def _header(self, method: str, path: str, body: bytes) -> str:
        created = int(current_clock().now().timestamp())
        nonce = b64url_encode(secrets.token_bytes(16))
        sig = b64url_encode(self.key.sign(signing_string(method, path, created, nonce, body)))
        return (
            f'keyid="{self.server_id}", alg="ed25519", created={created}, '
            f'nonce="{nonce}", sig="{sig}"'
        )

    def register(self, code: str, **override: Any) -> Any:
        document = {
            "registration_code": code,
            "server_id": self.server_id,
            "server_pubkey": self.public_key,
            "host_fingerprint": {"machine_id": "m1", "hostname": "h1"},
            "version": "1.0.0",
        } | override
        body = json.dumps(document).encode()
        return self.client.generic(
            "POST",
            REGISTER,
            body,
            content_type="application/json",
            HTTP_ALMI_SIGNATURE=self._header("POST", REGISTER, body),
        )

    def package(self, since_seq: int = 0) -> Any:
        path = f"/api/sync/v1/servers/{self.server_id}/package?since_seq={since_seq}"
        return self.client.get(path, HTTP_ALMI_SIGNATURE=self._header("GET", path, b""))


def claims(token: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(b64url_decode(token.split(".")[1]))
    return result


def header(token: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(b64url_decode(token.split(".")[0]))
    return result
