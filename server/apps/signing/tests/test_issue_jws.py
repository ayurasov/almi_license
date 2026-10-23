"""issue_jws (E02-03): header of section 6.1 of document 2, canonical payload, chain."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from apps.signing.domain import SigningUnavailable, install_provider, issue_jws
from infra.crypto.ed25519 import Ed25519Provider
from tests.vectors import DEV_ISSUER_CERT as DEV_CERT
from tests.vectors import b64url_decode, header_of, jws_vector, key_path, write_chain


def claims_of(name: str) -> dict[str, Any]:
    claims: dict[str, Any] = jws_vector(name)["expected"]["claims"]
    return claims


@pytest.fixture
def issuer() -> Iterator[Ed25519Provider]:
    provider = Ed25519Provider.from_files(key_path("dev-issuer.key"), DEV_CERT)
    install_provider(provider)
    yield provider
    install_provider(None)


@pytest.fixture
def local_server(tmp_path: Path) -> Iterator[Ed25519Provider]:
    chain = header_of(jws_vector("02-valid-local-server-lease")["jws"])["chain"]
    provider = Ed25519Provider.from_files(
        key_path("dev-local-server.key"), write_chain(tmp_path / "chain.jws", chain)
    )
    install_provider(provider)
    yield provider
    install_provider(None)


def test_header_and_canonical_payload(issuer: Ed25519Provider) -> None:
    claims = claims_of("01-valid-lease")

    header, payload, signature = issue_jws("alm-lease+jws", claims).split(".")

    assert (
        b64url_decode(header)
        == json.dumps(
            {
                "alg": "EdDSA",
                "chain": list(issuer.chain),
                "kid": "dev-issuer-1",
                "typ": "alm-lease+jws",
            },
            separators=(",", ":"),
        ).encode()
    )
    assert b64url_decode(payload) == json.dumps(
        claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert "«" in b64url_decode(payload).decode("utf-8")  # UTF-8, not \u escapes
    assert "=" not in header + payload + signature
    Ed25519PublicKey.from_public_bytes(issuer.public_key()).verify(
        b64url_decode(signature), f"{header}.{payload}".encode("ascii")
    )


def test_same_claims_give_the_same_bytes(issuer: Ed25519Provider) -> None:
    claims = claims_of("01-valid-lease")
    reordered = dict(reversed(list(claims.items())))

    assert issue_jws("alm-lease+jws", claims) == issue_jws("alm-lease+jws", reordered)


@pytest.mark.parametrize("typ", ["alm-lease", "JWT", "alm-unknown+jws"])
def test_unknown_typ_is_refused(issuer: Ed25519Provider, typ: str) -> None:
    with pytest.raises(ValueError, match="typ"):
        issue_jws(typ, {"ver": 1})


@pytest.mark.parametrize("claims", [{"x": float("nan")}, {"x": object()}, {1: "non-string key"}])
def test_claims_must_be_plain_json(issuer: Ed25519Provider, claims: dict[Any, Any]) -> None:
    with pytest.raises(ValueError):
        issue_jws("alm-lease+jws", claims)


def test_without_a_key_nothing_is_signed() -> None:
    install_provider(None)
    with pytest.raises(SigningUnavailable):
        issue_jws("alm-lease+jws", {"ver": 1})


def issued_vector(name: str, token: str) -> dict[str, Any]:
    """A vector in the contracts/vectors/jws format for an issued token (README there)."""
    reference = jws_vector(name)
    return {
        "name": f"issued-{name}",
        "description": f"Server issue_jws output for the claims of {name} (E02-03 cross-check)",
        "jws": token,
        "trust_roots": reference["trust_roots"],
        "now": reference["now"],
        "context": reference["context"],
        "expected": {"valid": True, "error": None, "claims": reference["expected"]["claims"]},
    }


def export(vector: dict[str, Any], tmp_path: Path) -> None:
    """make cross-verify sets ALMI_ISSUED_VECTORS_DIR; almi-keytool and lm_tests read it."""
    directory = Path(os.environ.get("ALMI_ISSUED_VECTORS_DIR") or tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{vector['name']}.json").write_text(
        json.dumps(vector, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_issued_central_lease_for_cross_verification(
    issuer: Ed25519Provider, tmp_path: Path
) -> None:
    token = issue_jws("alm-lease+jws", claims_of("01-valid-lease"))
    assert header_of(token)["chain"] == header_of(jws_vector("01-valid-lease")["jws"])["chain"]
    export(issued_vector("01-valid-lease", token), tmp_path)


def test_issued_local_server_lease_for_cross_verification(
    local_server: Ed25519Provider, tmp_path: Path
) -> None:
    name = "02-valid-local-server-lease"
    token = issue_jws("alm-lease+jws", claims_of(name))
    assert header_of(token)["kid"] == "srv_01JAB3K9M2N4P6Q8R0S2T4V6W8-1"
    assert len(header_of(token)["chain"]) == 2
    export(issued_vector(name, token), tmp_path)
