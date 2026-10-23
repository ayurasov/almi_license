"""Compact JWS signing and the reference check order of contracts/vectors/README.md.

The first failing step decides the result code; the payload is parsed only after the
signature is verified.
"""

import json
from dataclasses import dataclass
from typing import Any

import nacl.exceptions
from nacl.signing import SigningKey, VerifyKey

from almi_keytool.encoding import b64url, b64url_decode, canonical

ALG = "EdDSA"
CERT_TYP = "alm-cert+jws"
NBF_TOLERANCE = 24 * 3600

MALFORMED = "malformed"
ALG_UNSUPPORTED = "alg_unsupported"
TYP_INVALID = "typ_invalid"
CHAIN_INVALID = "chain_invalid"
KID_REVOKED = "kid_revoked"
CERT_EXPIRED = "cert_expired"
SIGNATURE_INVALID = "signature_invalid"
SCOPE_MISMATCH = "scope_mismatch"
AUDIENCE_MISMATCH = "audience_mismatch"
SUBJECT_MISMATCH = "subject_mismatch"
SEQ_NOT_GREATER = "seq_not_greater"
NOT_YET_VALID = "not_yet_valid"


@dataclass(frozen=True)
class LeaseContext:
    """State of the verifying product (vector field "context")."""

    product_code: str
    instance_id: str
    device_key_thumbprint: str
    stored_seq: int


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    error: str | None
    claims: dict[str, Any] | None


@dataclass(frozen=True)
class _Certificate:
    kid: str
    public_key: bytes
    nbf: int
    exp: int
    role: str
    scope: dict[str, Any] | None


class _Rejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sign(header: dict[str, Any], claims: dict[str, Any], key: SigningKey) -> str:
    signing_input = f"{b64url(canonical(header))}.{b64url(canonical(claims))}"
    return f"{signing_input}.{b64url(key.sign(signing_input.encode('ascii')).signature)}"


def _json_object(segment: str) -> dict[str, Any]:
    try:
        value = json.loads(b64url_decode(segment))
    except ValueError as error:
        raise _Rejected(MALFORMED) from error
    if not isinstance(value, dict):
        raise _Rejected(MALFORMED)
    return value


def _split(token: str) -> tuple[list[str], dict[str, Any]]:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise _Rejected(MALFORMED)
    header = _json_object(parts[0])
    if not all(isinstance(header.get(name), str) for name in ("alg", "typ", "kid")):
        raise _Rejected(MALFORMED)
    return parts, header


def _signature(parts: list[str]) -> bytes:
    try:
        signature = b64url_decode(parts[2])
    except ValueError as error:
        raise _Rejected(MALFORMED) from error
    if len(signature) != 64:
        raise _Rejected(MALFORMED)
    return signature


def _signature_valid(public_key: bytes, parts: list[str], signature: bytes) -> bool:
    try:
        VerifyKey(public_key).verify(f"{parts[0]}.{parts[1]}".encode("ascii"), signature)
    except nacl.exceptions.BadSignatureError:
        return False
    return True


def _walk_chain(chain: list[str], keys: dict[str, bytes]) -> list[_Certificate]:
    """Verify certificates from the root side; return them leaf first."""
    certificates: list[_Certificate] = []
    for token in reversed(chain):
        try:
            parts, header = _split(token)
            signature = _signature(parts)
        except _Rejected as rejected:
            raise _Rejected(CHAIN_INVALID) from rejected
        if header["alg"] != ALG or header["typ"] != CERT_TYP or header["kid"] not in keys:
            raise _Rejected(CHAIN_INVALID)
        if not _signature_valid(keys[header["kid"]], parts, signature):
            raise _Rejected(CHAIN_INVALID)
        claims = _json_object(parts[1])
        try:
            certificate = _Certificate(
                kid=str(claims["kid"]),
                public_key=b64url_decode(claims["pub"]),
                nbf=int(claims["nbf"]),
                exp=int(claims["exp"]),
                role=str(claims["role"]),
                scope=claims.get("scope"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise _Rejected(CHAIN_INVALID) from error
        keys[certificate.kid] = certificate.public_key
        certificates.insert(0, certificate)
    return certificates


def _check_lease(
    claims: dict[str, Any], leaf: _Certificate | None, lease: LeaseContext, now: int
) -> None:
    subject, lic = claims.get("subject") or {}, claims.get("lic") or {}
    if leaf is not None and leaf.role == "local_server":
        scope = leaf.scope or {}
        customer = (lic.get("customer") or {}).get("id")
        if claims.get("aud") not in scope.get("products", []) or customer != scope.get(
            "customer_id"
        ):
            raise _Rejected(SCOPE_MISMATCH)
    if claims.get("aud") != lease.product_code:
        raise _Rejected(AUDIENCE_MISMATCH)
    if (subject.get("instance_id"), subject.get("device_key_thumbprint")) != (
        lease.instance_id,
        lease.device_key_thumbprint,
    ):
        raise _Rejected(SUBJECT_MISMATCH)
    if not isinstance(claims.get("seq"), int) or claims["seq"] <= lease.stored_seq:
        raise _Rejected(SEQ_NOT_GREATER)
    if not isinstance(claims.get("nbf"), int) or claims["nbf"] > now + NBF_TOLERANCE:
        raise _Rejected(NOT_YET_VALID)


def _verify(
    token: str,
    roots: dict[str, bytes],
    now: int,
    revoked: set[str],
    expected_typ: str | None,
    lease: LeaseContext | None,
) -> dict[str, Any]:
    parts, header = _split(token)
    if header["alg"] != ALG:
        raise _Rejected(ALG_UNSUPPORTED)
    signature = _signature(parts)
    if expected_typ is not None and header["typ"] != expected_typ:
        raise _Rejected(TYP_INVALID)

    chain = header.get("chain", [])
    if not isinstance(chain, list) or not all(isinstance(item, str) for item in chain):
        raise _Rejected(MALFORMED)
    keys = dict(roots)
    certificates = _walk_chain(chain, keys)
    leaf = certificates[0] if certificates else None
    if leaf is not None and leaf.kid != header["kid"]:
        raise _Rejected(CHAIN_INVALID)
    if leaf is None and header["kid"] not in roots:
        raise _Rejected(CHAIN_INVALID)

    if {header["kid"], *(c.kid for c in certificates)} & revoked:
        raise _Rejected(KID_REVOKED)
    if any(not c.nbf <= now <= c.exp for c in certificates):
        raise _Rejected(CERT_EXPIRED)
    if not _signature_valid(keys[header["kid"]], parts, signature):
        raise _Rejected(SIGNATURE_INVALID)

    claims = _json_object(parts[1])
    if header["typ"] == CERT_TYP:
        if str(claims.get("kid")) in revoked:
            raise _Rejected(KID_REVOKED)
        if not (isinstance(claims.get("nbf"), int) and isinstance(claims.get("exp"), int)):
            raise _Rejected(MALFORMED)
        if not claims["nbf"] <= now <= claims["exp"]:
            raise _Rejected(CERT_EXPIRED)
    if lease is not None:
        _check_lease(claims, leaf, lease, now)
    return claims


def verify(
    token: str,
    roots: dict[str, bytes],
    *,
    now: int,
    revoked: set[str] | None = None,
    expected_typ: str | None = None,
    lease: LeaseContext | None = None,
) -> VerifyResult:
    """Check a compact JWS against embedded root keys; never raises on bad input."""
    try:
        claims = _verify(token, roots, now, revoked or set(), expected_typ, lease)
    except _Rejected as rejected:
        return VerifyResult(valid=False, error=rejected.code, claims=None)
    return VerifyResult(valid=True, error=None, claims=claims)


def header_of(token: str) -> dict[str, Any] | None:
    try:
        return _split(token)[1]
    except _Rejected:
        return None
