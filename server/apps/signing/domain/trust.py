"""Trust bundle of GET /api/v1/trust (E02-04; section 5.5 of document 2).

The bundle is made offline by almi-keytool export-trust and signed by the root key; the server only
serves it (TRUST_BUNDLE_FILE). It is checked against TRUST_ROOTS before it is served, and the
public fields must repeat the signed claims: the server never serves a bundle it cannot vouch for.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.signing.domain.verify import ChainInvalid, verify_signed
from infra.crypto.encoding import b64url_decode

TRUST_TYP = "alm-trust+jws"
FIELDS = ("roots", "issuers", "revoked_kids", "seq")


class TrustUnavailable(RuntimeError):
    """No valid trust bundle is configured on this server."""


def trust_roots() -> dict[str, bytes]:
    """TRUST_ROOTS as kid -> raw public key ("kid:pub" entries of the settings)."""
    roots: dict[str, bytes] = {}
    for entry in settings.TRUST_ROOTS:
        kid, _, pub = str(entry).partition(":")
        if kid and pub:
            roots[kid] = b64url_decode(pub)
    return roots


def trust_document(*, now: datetime) -> dict[str, Any]:
    path = settings.TRUST_BUNDLE_FILE
    if not path:
        raise TrustUnavailable("TRUST_BUNDLE_FILE is not set")
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TrustUnavailable(f"trust bundle is not readable: {error}") from None
    if not isinstance(document, dict) or not isinstance(document.get("bundle"), str):
        raise TrustUnavailable("trust bundle has no bundle")
    try:
        verified = verify_signed(document["bundle"], typ=TRUST_TYP, roots=trust_roots(), now=now)
    except ChainInvalid as error:
        raise TrustUnavailable(f"trust bundle does not verify: {error}") from None
    if verified.leaf is not None or any(document.get(k) != verified.claims.get(k) for k in FIELDS):
        raise TrustUnavailable("trust bundle fields differ from its signed claims")
    return {"bundle": document["bundle"], **{k: verified.claims[k] for k in FIELDS}}
