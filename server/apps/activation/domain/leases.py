"""LeaseIssuer: claims of a lease (section 6.2 of document 2) and their signature."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from apps.catalog.domain import ProductInfo
from apps.licensing.domain import LicenseRecord
from apps.policy.domain import PolicyParams, PolicyResult, lease_policy
from apps.signing.domain import issue_jws
from infra.crypto.encoding import b64url_encode

LEASE_TYP = "alm-lease+jws"


def rfc3339(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def device_key_thumbprint(device_pubkey: str) -> str:
    """RFC 7638 thumbprint of the Ed25519 device key (contracts/vectors/README.md)."""
    jwk = '{"crv":"Ed25519","kty":"OKP","x":"' + device_pubkey + '"}'
    return b64url_encode(hashlib.sha256(jwk.encode("ascii")).digest())


def lease_claims(
    *,
    issuer: str,
    activation_id: str,
    seq: int,
    now: datetime,
    product: ProductInfo,
    license_: LicenseRecord,
    edition: str | None,
    subject: dict[str, Any],
    capabilities: frozenset[str],
    policy: PolicyParams,
    result: PolicyResult,
) -> dict[str, Any]:
    unix = int(now.timestamp())
    lic: dict[str, Any] = {
        "id": str(license_.id),
        "type": license_.type,
        "status": license_.status,
        "valid_from": rfc3339(license_.valid_from),
        "valid_until": rfc3339(license_.valid_until),
        "support_until": rfc3339(license_.support_until),
        "customer": {"id": str(license_.customer_id), "name": license_.customer_name},
    }
    if edition is not None:
        lic["edition"] = edition
    claims: dict[str, Any] = {
        "ver": 1,
        "iss": issuer,
        "sub": activation_id,
        "aud": product.code,
        "iat": unix,
        "nbf": unix,
        "seq": seq,
        "lic": lic,
        "subject": subject,
        "limits": {},
        "capabilities": sorted(capabilities),
        "policy": lease_policy(policy),
        "messages": [],  # texts by message_ids come with E04-04
        "server_time": unix,
    }
    if result.lease_exp is not None:
        claims["exp"] = int(result.lease_exp.timestamp())
    return claims


def sign_lease(claims: dict[str, Any]) -> tuple[str, str]:
    """Compact JWS and the hash kept in Lease.jws_hash."""
    token = issue_jws(LEASE_TYP, claims)
    return token, hashlib.sha256(token.encode("ascii")).hexdigest()
