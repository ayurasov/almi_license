"""Offline files of devices (E08-01; section 10 of document 2, contracts/schemas/alk-*.json).

A .alk-req is a JSON container {format, version, payload} with a compact JWS alm-req+jws signed
by the device key carried in the payload itself (device_pubkey). The signature is checked before
any field of the payload is used; activate, renew and release then go through the same domain
services as the online API. The answer .alk-lic is signed by the issuing key.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils.dateparse import parse_datetime

from apps.activation.domain.keys import device_public_key
from apps.activation.domain.leases import rfc3339
from apps.signing.domain import issue_jws
from infra.crypto.ed25519 import Ed25519Provider
from infra.crypto.encoding import b64url_decode
from infra.errors import DomainError

MAX_FILE_BYTES = 64 * 1024
RESPONSE_DAYS = timedelta(days=30)
REQUEST_TYP = "alm-req+jws"
LICENSE_TYP = "alm-lic+jws"
DEVICE_TYPES = frozenset({"activate", "renew", "release"})
PUBLIC_KEY_SIZE, SIGNATURE_SIZE = 32, 64
MAX_NONCE = 128


@dataclass(frozen=True)
class OfflineRequest:
    """A verified payload of .alk-req: the signature matches its device_pubkey."""

    type: str
    payload: dict[str, Any]
    nonce: str
    created: datetime


def _invalid(detail: str) -> DomainError:
    return DomainError("invalid_request", detail)


def _json(data: bytes, what: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _invalid(f"{what} is not UTF-8 JSON") from None


def _segment(text: str, what: str) -> bytes:
    try:
        return b64url_decode(text)
    except ValueError:
        raise _invalid(f"{what} is not base64url") from None


def open_request(content: bytes, *, now: datetime) -> OfflineRequest:
    """Container, JWS header, device signature and age of the request; nothing else is trusted."""
    if len(content) > MAX_FILE_BYTES:
        raise _invalid("file is larger than 64 KiB")
    container = _json(content, "file")
    if (
        not isinstance(container, dict)
        or container.get("format") != "alk-req"
        or container.get("version") != 1
        or not isinstance(container.get("payload"), str)
    ):
        raise _invalid("not an alk-req file of version 1")
    parts = container["payload"].split(".")
    if len(parts) != 3:
        raise _invalid("payload is not a compact JWS")
    header = _json(_segment(parts[0], "JWS header"), "JWS header")
    if (
        not isinstance(header, dict)
        or header.get("alg") != "EdDSA"
        or header.get("typ") != REQUEST_TYP
    ):
        raise _invalid("JWS header is not alm-req+jws EdDSA")
    payload = _json(_segment(parts[1], "JWS payload"), "JWS payload")
    if not isinstance(payload, dict) or payload.get("type") not in DEVICE_TYPES:
        raise _invalid("request type is not activate, renew or release")
    key = payload.get("device_pubkey")
    raw_key = _segment(key, "device_pubkey") if isinstance(key, str) else b""
    signature = _segment(parts[2], "JWS signature")
    if len(raw_key) != PUBLIC_KEY_SIZE or len(signature) != SIGNATURE_SIZE:
        raise DomainError("signature_invalid")
    if not Ed25519Provider.verify(f"{parts[0]}.{parts[1]}".encode("ascii"), signature, raw_key):
        raise DomainError("signature_invalid")

    nonce, created_text = payload.get("nonce"), payload.get("created")
    created = parse_datetime(created_text) if isinstance(created_text, str) else None
    if not isinstance(nonce, str) or not 0 < len(nonce) <= MAX_NONCE or created is None:
        raise _invalid("nonce and created are required")
    if created.tzinfo is None:
        raise _invalid("created must carry a time zone")
    if now - created > RESPONSE_DAYS:
        raise _invalid("the request is older than 30 days: create a new one")
    if payload["type"] != "activate":
        stored = device_public_key(str(payload.get("activation_id", "")))
        if stored is None:
            raise DomainError("activation_not_found")
        if stored != key:
            raise DomainError("signature_invalid")
    return OfflineRequest(payload["type"], payload, nonce, created)


def answer(
    request: OfflineRequest,
    activation_id: str,
    *,
    now: datetime,
    lease: str | None = None,
    receipt: str | None = None,
) -> dict[str, Any]:
    """The .alk-lic container; the response is valid 30 days from the request."""
    start = min(request.created, now)
    claims: dict[str, Any] = {
        "request_nonce": request.nonce,
        "activation_id": activation_id,
        "issued_at": rfc3339(now),
        "respond_before": rfc3339(start + RESPONSE_DAYS),
    }
    if lease is not None:
        claims["lease"] = lease
    if receipt is not None:
        claims["receipt"] = receipt
    return {"format": "alk-lic", "version": 1, "payload": issue_jws(LICENSE_TYP, claims)}
