"""Verification of a JWS with its certificate chain up to a trusted root (E09-03).

The same rules as LeaseVerifier of the DL module (contracts/vectors/README.md, steps 1–8): every
certificate of header.chain is signed by the next one or by a root, the leaf certifies the kid of
the header, certificates are valid at now, the signature is checked with the leaf key before the
payload is parsed. A local server checks its packages this way.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from infra.crypto.ed25519 import Ed25519Provider
from infra.crypto.encoding import b64url_decode

CERT_TYP = "alm-cert+jws"
SIGNATURE_SIZE = 64


class ChainInvalid(ValueError):
    """The token does not verify up to a trusted root; str() is the result code."""


@dataclass(frozen=True)
class Verified:
    claims: dict[str, Any]
    leaf: dict[str, Any] | None


def _parts(token: str) -> tuple[dict[str, Any], str, bytes, str]:
    pieces = token.split(".")
    if len(pieces) != 3:
        raise ChainInvalid("malformed")
    try:
        header = json.loads(b64url_decode(pieces[0]))
        signature = b64url_decode(pieces[2])
    except ValueError:
        raise ChainInvalid("malformed") from None
    if not isinstance(header, dict):
        raise ChainInvalid("malformed")
    return header, f"{pieces[0]}.{pieces[1]}", signature, pieces[1]


def _payload(segment: str) -> dict[str, Any]:
    try:
        value = json.loads(b64url_decode(segment))
    except ValueError:
        raise ChainInvalid("malformed") from None
    if not isinstance(value, dict):
        raise ChainInvalid("malformed")
    return value


def verify_signed(
    token: str,
    *,
    typ: str,
    roots: dict[str, bytes],
    now: datetime,
    revoked: frozenset[str] = frozenset(),
) -> Verified:
    header, signing_input, signature, payload = _parts(token)
    if header.get("alg") != "EdDSA":
        raise ChainInvalid("alg_unsupported")
    if len(signature) != SIGNATURE_SIZE:
        raise ChainInvalid("malformed")
    if header.get("typ") != typ:
        raise ChainInvalid("typ_invalid")
    chain = header.get("chain", [])
    if not isinstance(chain, list) or not all(isinstance(item, str) for item in chain):
        raise ChainInvalid("malformed")
    keys = dict(roots)
    certificates: list[dict[str, Any]] = []
    for item in reversed(chain):
        cert_header, cert_input, cert_signature, cert_payload = _parts(item)
        signer = keys.get(str(cert_header.get("kid", "")))
        if (
            cert_header.get("alg") != "EdDSA"
            or len(cert_signature) != SIGNATURE_SIZE
            or cert_header.get("typ") != CERT_TYP
            or signer is None
            or not Ed25519Provider.verify(cert_input.encode("ascii"), cert_signature, signer)
        ):
            raise ChainInvalid("chain_invalid")
        claims = _payload(cert_payload)
        try:
            pub = b64url_decode(str(claims["pub"]))
            kid, nbf, exp = str(claims["kid"]), int(claims["nbf"]), int(claims["exp"])
        except (KeyError, TypeError, ValueError):
            raise ChainInvalid("chain_invalid") from None
        if len(pub) != 32:
            raise ChainInvalid("chain_invalid")
        keys[kid] = pub
        certificates.insert(0, claims | {"nbf": nbf, "exp": exp})
    kid = str(header.get("kid", ""))
    leaf = certificates[0] if certificates else None
    if (leaf is not None and leaf["kid"] != kid) or (leaf is None and kid not in roots):
        raise ChainInvalid("chain_invalid")
    if kid in revoked or any(c["kid"] in revoked for c in certificates):
        raise ChainInvalid("kid_revoked")
    moment = int(now.timestamp())
    if any(moment < c["nbf"] or moment > c["exp"] for c in certificates):
        raise ChainInvalid("cert_expired")
    if not Ed25519Provider.verify(signing_input.encode("ascii"), signature, keys[kid]):
        raise ChainInvalid("signature_invalid")
    return Verified(_payload(payload), leaf)
