"""Certificates alm-cert+jws issued by the issuer key (E09-02; contracts/schemas/cert.schema.json).

A local server certificate (role local_server) carries its scope: the customer, the products and
the seats by license; the product checks a lease of the local server against that scope.
"""

from datetime import datetime
from typing import Any

from apps.signing.domain.jws import current_provider, issue_jws

CERT_TYP = "alm-cert+jws"


def issue_certificate(
    *,
    kid: str,
    public_key: str,
    role: str,
    not_before: datetime,
    expires: datetime,
    scope: dict[str, Any] | None = None,
) -> str:
    claims: dict[str, Any] = {
        "ver": 1,
        "kid": kid,
        "alg": "EdDSA",
        "pub": public_key,
        "role": role,
        "iss": current_provider().kid,
        "iat": int(not_before.timestamp()),
        "nbf": int(not_before.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if scope is not None:
        claims["scope"] = scope
    return issue_jws(CERT_TYP, claims)


def issuer_chain() -> tuple[str, ...]:
    """Certificates of the issuer key, its own first (the trust part of a package)."""
    return current_provider().chain
