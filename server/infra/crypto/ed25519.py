"""Ed25519Provider: CryptoProvider on the cryptography library (E02-02).

The issuer key comes from SIGNING_KEY_FILE (Docker secret): a 32-byte Ed25519 seed in
base64url, the format of almi-keytool and contracts/vectors/keys. SIGNING_CERT_FILE holds
the certificate chain (compact alm-cert+jws, one per line, the key's own certificate first);
the key's kid is taken from the first certificate, which must certify this very key.

The private key never reaches repr, logs, exceptions, pickles or copies.
"""

import json
from pathlib import Path
from typing import Any, NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from infra.crypto.encoding import b64url_decode, b64url_encode

CERT_TYP = "alm-cert+jws"
SEED_SIZE = 32


class SigningKeyError(Exception):
    """The key or certificate file cannot be used; the message never carries their content."""


def _fail(message: str) -> NoReturn:
    raise SigningKeyError(message)


def _read(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="ascii")
    except FileNotFoundError:
        _fail(f"{what} {path}: file is missing")
    except (OSError, UnicodeDecodeError):
        _fail(f"{what} {path}: file is not readable as ASCII")


def _load_seed(path: Path) -> Ed25519PrivateKey:
    text = _read(path, "SIGNING_KEY_FILE")
    try:
        seed = b64url_decode(text.strip())
    except ValueError:
        seed = b""
    if len(seed) != SEED_SIZE:
        _fail(f"SIGNING_KEY_FILE {path}: not a base64url Ed25519 seed of {SEED_SIZE} bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def _certificate_claims(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        header = json.loads(b64url_decode(parts[0]))
        claims = json.loads(b64url_decode(parts[1]))
    except ValueError:
        return None
    if not isinstance(header, dict) or header.get("typ") != CERT_TYP:
        return None
    if not isinstance(claims, dict) or not isinstance(claims.get("kid"), str):
        return None
    return claims


def _raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class Ed25519Provider:
    __slots__ = ("_chain", "_key", "_kid")

    def __init__(self, key: Ed25519PrivateKey, kid: str, chain: tuple[str, ...]) -> None:
        self._key = key
        self._kid = kid
        self._chain = chain

    @classmethod
    def from_files(cls, key_file: Path, cert_file: Path) -> "Ed25519Provider":
        key = _load_seed(key_file)
        chain = tuple(_read(cert_file, "SIGNING_CERT_FILE").split())
        claims = [_certificate_claims(token) for token in chain]
        leaf = claims[0] if claims else None
        if leaf is None or None in claims:
            _fail(f"SIGNING_CERT_FILE {cert_file}: expected {CERT_TYP} certificates, one per line")
        if leaf.get("pub") != b64url_encode(_raw_public(key)):
            _fail(f"SIGNING_CERT_FILE {cert_file}: the first certificate does not certify the key")
        return cls(key, leaf["kid"], chain)

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def chain(self) -> tuple[str, ...]:
        return self._chain

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload)

    def verify(self, payload: bytes, signature: bytes, public_key: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
        except (InvalidSignature, ValueError):
            return False
        return True

    def public_key(self) -> bytes:
        return _raw_public(self._key)

    def __repr__(self) -> str:
        return f"Ed25519Provider(kid={self._kid!r})"

    def __reduce__(self) -> NoReturn:
        raise TypeError("Ed25519Provider holds a private key and cannot be serialised")

    def __copy__(self) -> NoReturn:
        raise TypeError("Ed25519Provider holds a private key and cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("Ed25519Provider holds a private key and cannot be copied")
