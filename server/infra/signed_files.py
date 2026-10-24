"""Offline files: a UTF-8 JSON container {format, version, payload} with a compact JWS inside
(section 10 of document 2). The JWS is signed by a key carried in its own payload (a device or a
local server that the receiver may not know yet), so the signature is checked with that key
before any other field of the payload is used."""

import json
from dataclasses import dataclass
from typing import Any

from infra.crypto.ed25519 import Ed25519Provider
from infra.crypto.encoding import b64url_decode

PUBLIC_KEY_SIZE, SIGNATURE_SIZE = 32, 64


class FileRefused(ValueError):
    """The file is not a container of the expected kind (400 invalid_request)."""


class SignatureMismatch(ValueError):
    """The JWS does not verify with the key of its payload (401 signature_invalid)."""


@dataclass(frozen=True)
class SignedFile:
    header: dict[str, Any]
    payload: dict[str, Any]


def _json(data: bytes, what: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FileRefused(f"{what} is not UTF-8 JSON") from None


def _segment(text: str, what: str) -> bytes:
    try:
        return b64url_decode(text)
    except ValueError:
        raise FileRefused(f"{what} is not base64url") from None


def open_signed_file(
    content: bytes, *, file_format: str, typ: str, key_field: str, max_bytes: int
) -> SignedFile:
    if len(content) > max_bytes:
        raise FileRefused(f"file is larger than {max_bytes // 1024} KiB")
    container = _json(content, "file")
    if (
        not isinstance(container, dict)
        or container.get("format") != file_format
        or container.get("version") != 1
        or not isinstance(container.get("payload"), str)
    ):
        raise FileRefused(f"not a {file_format} file of version 1")
    parts = container["payload"].split(".")
    if len(parts) != 3:
        raise FileRefused("payload is not a compact JWS")
    header = _json(_segment(parts[0], "JWS header"), "JWS header")
    if not isinstance(header, dict) or header.get("alg") != "EdDSA" or header.get("typ") != typ:
        raise FileRefused(f"JWS header is not {typ} EdDSA")
    payload = _json(_segment(parts[1], "JWS payload"), "JWS payload")
    if not isinstance(payload, dict):
        raise FileRefused("JWS payload is not an object")
    key = payload.get(key_field)
    raw_key = _segment(key, key_field) if isinstance(key, str) else b""
    signature = _segment(parts[2], "JWS signature")
    if len(raw_key) != PUBLIC_KEY_SIZE or len(signature) != SIGNATURE_SIZE:
        raise SignatureMismatch(key_field)
    if not Ed25519Provider.verify(f"{parts[0]}.{parts[1]}".encode("ascii"), signature, raw_key):
        raise SignatureMismatch(key_field)
    return SignedFile(header, payload)
