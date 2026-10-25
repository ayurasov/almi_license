"""Trust bundle: the /api/v1/trust document with alm-trust+jws signed by the root key."""

from typing import Any

from almi_keytool.encoding import b64url
from almi_keytool.jws import sign
from almi_keytool.rootkey import RootKey

TRUST_TYP = "alm-trust+jws"


def build_trust(
    root: RootKey,
    *,
    issuers: list[str],
    revoked_kids: list[str],
    seq: int,
    iat: int,
    reserve_roots: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    roots = [{"kid": root.kid, "alg": "EdDSA", "pub": b64url(root.public_key), "status": "active"}]
    roots += [dict(item, status="reserve") for item in reserve_roots or []]
    claims = {
        "ver": 1,
        "seq": seq,
        "iat": iat,
        "roots": roots,
        "issuers": issuers,
        "revoked_kids": revoked_kids,
    }
    bundle = sign({"alg": "EdDSA", "typ": TRUST_TYP, "kid": root.kid}, claims, root.signing_key)
    return {
        "bundle": bundle,
        "roots": roots,
        "issuers": issuers,
        "revoked_kids": revoked_kids,
        "seq": seq,
    }
