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


def _cert(signer: SigningKey, signer_kid: str, subject: SigningKey, role: str, kid: str) -> str:
    scope = None
    if role == "local_server":
        scope = {"server_id": "srv_x", "customer_id": "c", "products": [], "quotas": {}}
    return issue_certificate(
        signer,
        signer_kid,
        bytes(subject.verify_key),
        role=role,
        kid=kid,
        iat=NOW - DAY,
        valid_days=10,
        scope=scope,
    )


def test_local_server_key_signs_no_certificate() -> None:
    """Document 1, §12: the key of a customer's local server cannot make an issuer of its own."""
    root, issuer, server, attacker = (SigningKey.generate() for _ in range(4))
    issuer_cert = _cert(root, "root", issuer, "issuer", "iss-1")
    server_cert = _cert(issuer, "iss-1", server, "local_server", "srv-1")
    roots = {"root": bytes(root.verify_key)}
    genuine = lease_signed_by(server, "srv-1", [server_cert, issuer_cert])
    assert verify(genuine, roots, now=NOW).valid
    for role in ("issuer", "local_server"):
        forged = _cert(server, "srv-1", attacker, role, "evil-1")
        token = lease_signed_by(attacker, "evil-1", [forged, server_cert, issuer_cert])
        result = verify(token, roots, now=NOW)
        assert (result.valid, result.error) == (False, CHAIN_INVALID), role


def test_issuer_signs_no_issuer_and_no_known_kid() -> None:
    root, issuer, attacker = SigningKey.generate(), SigningKey.generate(), SigningKey.generate()
    issuer_cert = _cert(root, "root", issuer, "issuer", "iss-1")
    roots = {"root": bytes(root.verify_key)}
    forged = _cert(issuer, "iss-1", attacker, "issuer", "evil-1")
    result = verify(lease_signed_by(attacker, "evil-1", [forged, issuer_cert]), roots, now=NOW)
    assert (result.valid, result.error) == (False, CHAIN_INVALID)
    # A certificate named like the root would replace the root key for the rest of the chain.
    shadow = _cert(issuer, "iss-1", attacker, "local_server", "root")
    result = verify(lease_signed_by(attacker, "root", [shadow, issuer_cert]), roots, now=NOW)
    assert (result.valid, result.error) == (False, CHAIN_INVALID)
