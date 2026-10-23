"""P7 attack scenarios beyond the vectors: forged chains, substituted leaves (docs/specs/06, 8)."""

from nacl.signing import SigningKey

from almi_keytool.certs import issue_certificate
from almi_keytool.jws import CHAIN_INVALID, verify
from almi_keytool.jws import sign as jws_sign

NOW = 1762071300
DAY = 86400


def lease_signed_by(key: SigningKey, kid: str, chain: list[str]) -> str:
    claims = {"ver": 1, "seq": 1, "nbf": NOW}
    return jws_sign(
        {"alg": "EdDSA", "typ": "alm-lease+jws", "kid": kid, "chain": chain}, claims, key
    )


def test_certificate_from_an_unknown_root_is_rejected() -> None:
    real_root, fake_root, issuer = (
        SigningKey.generate(),
        SigningKey.generate(),
        SigningKey.generate(),
    )
    forged = issue_certificate(
        fake_root,
        "root",
        bytes(issuer.verify_key),
        role="issuer",
        kid="c-1",
        iat=NOW - DAY,
        valid_days=10,
    )

    result = verify(
        lease_signed_by(issuer, "c-1", [forged]), {"root": bytes(real_root.verify_key)}, now=NOW
    )

    assert (result.valid, result.error) == (False, CHAIN_INVALID)


def test_leaf_must_certify_the_signing_kid() -> None:
    root, issuer, attacker = SigningKey.generate(), SigningKey.generate(), SigningKey.generate()
    genuine = issue_certificate(
        root,
        "root",
        bytes(issuer.verify_key),
        role="issuer",
        kid="c-1",
        iat=NOW - DAY,
        valid_days=10,
    )

    # A genuine certificate for c-1 cannot vouch for a lease signed under another kid.
    result = verify(
        lease_signed_by(attacker, "c-2", [genuine]), {"root": bytes(root.verify_key)}, now=NOW
    )

    assert (result.valid, result.error) == (False, CHAIN_INVALID)


def test_unknown_kid_without_chain_is_rejected() -> None:
    root, other = SigningKey.generate(), SigningKey.generate()

    result = verify(
        lease_signed_by(other, "someone", []), {"root": bytes(root.verify_key)}, now=NOW
    )

    assert (result.valid, result.error) == (False, CHAIN_INVALID)
