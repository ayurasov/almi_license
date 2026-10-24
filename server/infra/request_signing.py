"""String to sign of ALMI-Signature (section 4.4 of document 2), shared by the verifier of the
Product and Sync API and by a local server that signs its requests to the central server."""

import hashlib

from infra.crypto.encoding import b64url_encode

VERSION = b"ALMI-REQ-V1"


def body_digest(body: bytes) -> str:
    return b64url_encode(hashlib.sha256(body).digest())


def signing_string(method: str, path: str, created: int, nonce: str, body: bytes) -> bytes:
    lines = [VERSION.decode(), method.upper(), path, str(created), nonce, body_digest(body)]
    return "\n".join(lines).encode("utf-8")


def signature_header(keyid: str, created: int, nonce: str, sig: str) -> str:
    return f'keyid="{keyid}", alg="ed25519", created={created}, nonce="{nonce}", sig="{sig}"'
