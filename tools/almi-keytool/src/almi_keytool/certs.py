"""Key certificates alm-cert+jws (contracts/schemas/cert.schema.json)."""

from typing import Any

from nacl.signing import SigningKey

from almi_keytool.encoding import b64url
from almi_keytool.jws import CERT_TYP, sign

DAY = 86400
ROLES = ("issuer", "local_server")
MAX_VALID_DAYS = 3650


def issue_certificate(
    signer: SigningKey,
    signer_kid: str,
    subject_public_key: bytes,
    *,
    role: str,
    kid: str,
    iat: int,
    valid_days: int,
    scope: dict[str, Any] | None = None,
) -> str:
    """Sign a certificate for subject_public_key, valid from iat for valid_days days."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not kid or kid == signer_kid:
        raise ValueError("kid must be set and differ from the signer's kid")
    if not 1 <= valid_days <= MAX_VALID_DAYS:
        raise ValueError(f"valid days must be between 1 and {MAX_VALID_DAYS}")
    if len(subject_public_key) != 32:
        raise ValueError("subject public key must be 32 bytes (Ed25519)")
    if (role == "local_server") != (scope is not None):
        raise ValueError("scope is required for local_server certificates and only for them")
    claims: dict[str, Any] = {
        "ver": 1,
        "alg": "EdDSA",
        "pub": b64url(subject_public_key),
        "iss": signer_kid,
        "kid": kid,
        "role": role,
        "iat": iat,
        "nbf": iat,
        "exp": iat + valid_days * DAY,
    }
    if scope is not None:
        claims["scope"] = scope
    return sign({"alg": "EdDSA", "typ": CERT_TYP, "kid": signer_kid}, claims, signer)
