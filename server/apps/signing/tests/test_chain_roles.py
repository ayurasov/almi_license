"""Roles of the certificate chain (section 6.3 of document 2; document 1, §12 «ограниченный
сертификат»): a local server key cannot certify itself or anyone else as an issuer.

The tokens are built with the dev keys of contracts/vectors/keys around the chain of the vector
02-valid-local-server-lease; the vectors themselves keep passing (test_verify.py).
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from apps.signing.domain import ChainInvalid, verify_signed
from tests.vectors import b64url_decode, header_of, jws_vector, key_path

LEASE = "alm-lease+jws"
VECTOR = jws_vector("02-valid-local-server-lease")
CHAIN: list[str] = header_of(VECTOR["jws"])["chain"]  # [srv cert, issuer cert]
SERVER_KID = header_of(VECTOR["jws"])["kid"]
ROOTS = {r["kid"]: b64url_decode(r["pub"]) for r in VECTOR["trust_roots"]}
NOW = datetime.fromtimestamp(VECTOR["now"], UTC)
CLAIMS: dict[str, Any] = json.loads(b64url_decode(VECTOR["jws"].split(".")[1]))


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _key(name: str) -> Ed25519PrivateKey:
    seed = b64url_decode(key_path(f"{name}.key").read_text(encoding="ascii").strip())
    return Ed25519PrivateKey.from_private_bytes(seed)


def _pub(key: Ed25519PrivateKey) -> str:
    return _b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def _jws(header: dict[str, Any], claims: dict[str, Any], key: Ed25519PrivateKey) -> str:
    def part(value: dict[str, Any]) -> str:
        return _b64(json.dumps(value, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{part(header)}.{part(claims)}"
    return f"{signing_input}.{_b64(key.sign(signing_input.encode('ascii')))}"


def _cert(signer: Ed25519PrivateKey, signer_kid: str, kid: str, pub: str, role: str) -> str:
    claims = {
        "ver": 1,
        "alg": "EdDSA",
        "pub": pub,
        "iss": signer_kid,
        "kid": kid,
        "role": role,
        "iat": VECTOR["now"] - 60,
        "nbf": VECTOR["now"] - 60,
        "exp": VECTOR["now"] + 86400,
    }
    if role == "local_server":
        claims["scope"] = {"server_id": "srv_x", "customer_id": "c", "products": [], "quotas": {}}
    return _jws({"alg": "EdDSA", "typ": "alm-cert+jws", "kid": signer_kid}, claims, signer)


def _token(key: Ed25519PrivateKey, kid: str, chain: list[str], typ: str = LEASE) -> str:
    return _jws({"alg": "EdDSA", "typ": typ, "kid": kid, "chain": chain}, CLAIMS, key)


EVIL = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def test_the_vector_chain_still_verifies() -> None:
    verified = verify_signed(VECTOR["jws"], typ=LEASE, roots=ROOTS, now=NOW)
    assert verified.leaf is not None and verified.leaf["role"] == "local_server"


@pytest.mark.parametrize("role", ["issuer", "local_server"])
def test_local_server_key_signs_no_certificate(role: str) -> None:
    """The key of a customer's local server makes an «issuer» (or another server) of its own."""
    forged = _cert(_key("dev-local-server"), SERVER_KID, "evil-1", _pub(EVIL), role)
    token = _token(EVIL, "evil-1", [forged, *CHAIN])
    with pytest.raises(ChainInvalid, match="chain_invalid"):
        verify_signed(token, typ=LEASE, roots=ROOTS, now=NOW)


def test_issuer_signs_no_issuer() -> None:
    forged = _cert(_key("dev-issuer"), "dev-issuer-1", "evil-1", _pub(EVIL), "issuer")
    token = _token(EVIL, "evil-1", [forged, CHAIN[1]])
    with pytest.raises(ChainInvalid, match="chain_invalid"):
        verify_signed(token, typ=LEASE, roots=ROOTS, now=NOW)


def test_certificate_cannot_replace_a_known_kid() -> None:
    """A certificate named like the root would replace its key for the rest of the chain."""
    forged = _cert(_key("dev-issuer"), "dev-issuer-1", "dev-root", _pub(EVIL), "local_server")
    token = _token(EVIL, "dev-root", [forged, CHAIN[1]])
    with pytest.raises(ChainInvalid, match="chain_invalid"):
        verify_signed(token, typ=LEASE, roots=ROOTS, now=NOW)


def test_issuer_signed_local_server_certificate_is_accepted() -> None:
    valid = _cert(_key("dev-issuer"), "dev-issuer-1", "srv-2", _pub(EVIL), "local_server")
    verified = verify_signed(
        _token(EVIL, "srv-2", [valid, CHAIN[1]]), typ=LEASE, roots=ROOTS, now=NOW
    )
    assert verified.leaf is not None and verified.leaf["kid"] == "srv-2"


def test_package_signed_by_a_local_server_key_is_refused() -> None:
    """A package is issued by the central server: a local server cannot sign its own rights."""
    typ = "alm-package+jws"
    token = _token(_key("dev-local-server"), SERVER_KID, CHAIN, typ)
    with pytest.raises(ChainInvalid, match="chain_invalid"):
        verify_signed(token, typ=typ, roots=ROOTS, now=NOW, leaf_roles=frozenset({"issuer"}))
    issued = _token(_key("dev-issuer"), "dev-issuer-1", [CHAIN[1]], typ)
    verified = verify_signed(
        issued, typ=typ, roots=ROOTS, now=NOW, leaf_roles=frozenset({"issuer"})
    )
    assert verified.leaf is not None and verified.leaf["role"] == "issuer"
