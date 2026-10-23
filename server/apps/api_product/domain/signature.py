"""ALMI-Signature: request signature with the device key (section 4.4 of document 2, E05-01).

Order of checks: header format, alg, nonce format, clock window, signature, nonce replay.
A nonce is remembered only after a valid signature, so forged requests cannot use up nonces.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction

from apps.api_product.models import RequestNonce
from infra.crypto.ed25519 import Ed25519Provider
from infra.crypto.encoding import b64url_decode, b64url_encode

VERSION = b"ALMI-REQ-V1"
ALG = "ed25519"
DEVICE_KEYID = "device"
CLOCK_TOLERANCE = timedelta(seconds=300)
NONCE_WINDOW = timedelta(seconds=600)
NONCE_SIZE = 16
PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64

_PARAM = re.compile(r'\s*([a-z]+)=(?:"([^"]*)"|([0-9]+))\s*')
_FIELDS = {"keyid": str, "alg": str, "created": int, "nonce": str, "sig": str}


class SignatureInvalid(Exception):
    """401 signature_invalid."""


class ClockSkew(Exception):
    """401 clock_skew; the response carries server_time."""

    def __init__(self, server_time: datetime) -> None:
        super().__init__("created is outside the allowed clock skew")
        self.server_time = server_time


@dataclass(frozen=True)
class SignatureHeader:
    keyid: str
    alg: str
    created: int
    nonce: str
    sig: str


def parse_header(value: str) -> SignatureHeader:
    """Exactly the five parameters, each once; keyid, alg, nonce, sig quoted, created a number."""
    values: dict[str, str | int] = {}
    for part in value.split(","):
        match = _PARAM.fullmatch(part)
        if match is None:
            raise SignatureInvalid("malformed ALMI-Signature")
        name, quoted, number = match.groups()
        kind = _FIELDS.get(name)
        if kind is None or name in values or (kind is int) != (number is not None):
            raise SignatureInvalid("malformed ALMI-Signature")
        values[name] = int(number) if number is not None else quoted
    if values.keys() != _FIELDS.keys():
        raise SignatureInvalid("malformed ALMI-Signature")
    return SignatureHeader(
        keyid=str(values["keyid"]),
        alg=str(values["alg"]),
        created=int(values["created"]),
        nonce=str(values["nonce"]),
        sig=str(values["sig"]),
    )


def body_digest(body: bytes) -> str:
    return b64url_encode(hashlib.sha256(body).digest())


def signing_string(method: str, path: str, created: int, nonce: str, body: bytes) -> bytes:
    lines = [VERSION.decode(), method.upper(), path, str(created), nonce, body_digest(body)]
    return "\n".join(lines).encode("utf-8")


def _decode(text: str, size: int) -> bytes:
    try:
        data = b64url_decode(text)
    except ValueError:
        raise SignatureInvalid("not base64url") from None
    if len(data) != size:
        raise SignatureInvalid("wrong length")
    return data


def verify_request(
    header: SignatureHeader,
    *,
    method: str,
    path: str,
    body: bytes,
    public_key: str,
    now: datetime,
) -> None:
    """Raise SignatureInvalid or ClockSkew; on success the nonce is remembered."""
    if header.alg != ALG:
        raise SignatureInvalid("unsupported alg")
    _decode(header.nonce, NONCE_SIZE)
    created = datetime.fromtimestamp(header.created, UTC)
    if abs(created - now) > CLOCK_TOLERANCE:
        raise ClockSkew(now)
    message = signing_string(method, path, header.created, header.nonce, body)
    if not Ed25519Provider.verify(
        message, _decode(header.sig, SIGNATURE_SIZE), _decode(public_key, PUBLIC_KEY_SIZE)
    ):
        raise SignatureInvalid("signature does not match")
    _remember_nonce(header.keyid, header.nonce, now)


def _remember_nonce(keyid: str, nonce: str, now: datetime) -> None:
    try:
        with transaction.atomic():
            RequestNonce.objects.create(keyid=keyid, nonce=nonce, created_at=now)
    except IntegrityError:
        raise SignatureInvalid("nonce replay") from None


def purge_nonces(now: datetime) -> int:
    """Delete nonces older than the replay window; run by the background job (E12-01)."""
    deleted, _ = RequestNonce.objects.filter(created_at__lt=now - NONCE_WINDOW).delete()
    return deleted
