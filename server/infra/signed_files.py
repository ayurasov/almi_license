"""Offline files: a UTF-8 JSON container {format, version, payload} with a compact JWS inside
(section 10 of document 2). The JWS is signed by a key carried in its own payload (a device or a
local server that the receiver may not know yet), so the signature is checked with that key
before any other field of the payload is used."""

import json
from collections.abc import Callable
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


@dataclass(frozen=True)
class _Parsed:
    header: dict[str, Any]
    payload: dict[str, Any]
    signing_input: bytes
    signature: bytes


def _parse(content: bytes, *, file_format: str, typ: str, max_bytes: int) -> _Parsed:
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
    signature = _segment(parts[2], "JWS signature")
    return _Parsed(header, payload, f"{parts[0]}.{parts[1]}".encode("ascii"), signature)


def _verify(parsed: _Parsed, raw_key: bytes, what: str) -> SignedFile:
    if len(raw_key) != PUBLIC_KEY_SIZE or len(parsed.signature) != SIGNATURE_SIZE:
        raise SignatureMismatch(what)
    if not Ed25519Provider.verify(parsed.signing_input, parsed.signature, raw_key):
        raise SignatureMismatch(what)
    return SignedFile(parsed.header, parsed.payload)


def open_signed_file(
    content: bytes, *, file_format: str, typ: str, key_field: str, max_bytes: int
) -> SignedFile:
    """The JWS is checked with the key in its own payload field key_field."""
    parsed = _parse(content, file_format=file_format, typ=typ, max_bytes=max_bytes)
    key = parsed.payload.get(key_field)
    raw_key = _segment(key, key_field) if isinstance(key, str) else b""
    return _verify(parsed, raw_key, key_field)


def open_file_of_known_key(
    content: bytes,
    *,
    file_format: str,
    typ: str,
    max_bytes: int,
    key_of: Callable[[str], bytes | None],
) -> SignedFile:
    """The JWS is checked with the key the receiver keeps for the kid of the header (a .alk-usage
    of a registered local server); an unknown kid is a signature mismatch."""
    parsed = _parse(content, file_format=file_format, typ=typ, max_bytes=max_bytes)
    kid = parsed.header.get("kid")
    raw_key = key_of(kid) if isinstance(kid, str) else None
    return _verify(parsed, raw_key or b"", "kid")
