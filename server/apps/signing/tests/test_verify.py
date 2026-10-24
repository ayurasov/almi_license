"""verify_signed against the JWS vectors: steps 1–8 give the same result codes as LeaseVerifier.

Steps 9–14 (lease payload, scope, audience, subject, seq) are product checks, not part of it.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from apps.signing.domain import ChainInvalid, verify_signed
from tests.vectors import VECTORS, b64url_decode, jws_vector

CHAIN_CODES = {
    "malformed",
    "alg_unsupported",
    "typ_invalid",
    "chain_invalid",
    "kid_revoked",
    "cert_expired",
    "signature_invalid",
}
NAMES = sorted(p.stem for p in (VECTORS / "jws").glob("*.json"))


@pytest.mark.parametrize("name", NAMES)
def test_vectors(name: str) -> None:
    vector = jws_vector(name)
    roots = {r["kid"]: b64url_decode(r["pub"]) for r in vector["trust_roots"]}
    now = datetime.fromtimestamp(vector["now"], UTC)
    revoked = frozenset(vector["context"].get("revoked_kids", []))
    expected = vector["expected"]
    try:
        verified = verify_signed(
            vector["jws"], typ="alm-lease+jws", roots=roots, now=now, revoked=revoked
        )
    except ChainInvalid as error:
        assert not expected["valid"]
        assert str(error) == expected["error"]
        return
    if expected["valid"]:
        assert verified.claims == expected["claims"]
    else:
        assert expected["error"] not in CHAIN_CODES, Path(name)
