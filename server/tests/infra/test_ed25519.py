"""Ed25519Provider (E02-02): dev issuer key and certificate from contracts/vectors."""

import copy
import pickle
from pathlib import Path

import pytest

from infra.crypto.ed25519 import Ed25519Provider, SigningKeyError
from tests.vectors import DEV_ISSUER_CERT as DEV_CERT
from tests.vectors import b64url_decode, header_of, jws_vector, key_path, public_key, write_chain


@pytest.fixture
def provider() -> Ed25519Provider:
    return Ed25519Provider.from_files(key_path("dev-issuer.key"), DEV_CERT)


def test_dev_certificate_is_the_one_in_the_vectors() -> None:
    chain = header_of(jws_vector("01-valid-lease")["jws"])["chain"]
    assert DEV_CERT.read_text(encoding="ascii").split() == chain


def test_kid_chain_and_public_key_come_from_the_files(provider: Ed25519Provider) -> None:
    assert provider.kid == "dev-issuer-1"
    assert provider.chain == tuple(DEV_CERT.read_text(encoding="ascii").split())
    assert provider.public_key() == public_key("dev-issuer")


def test_signature_matches_the_reference_vector(provider: Ed25519Provider) -> None:
    """Ed25519 is deterministic: the same signing input gives the vector's signature (PyNaCl)."""
    header, payload, signature = jws_vector("01-valid-lease")["jws"].split(".")

    assert provider.sign(f"{header}.{payload}".encode("ascii")) == b64url_decode(signature)


def test_verify(provider: Ed25519Provider) -> None:
    signature = provider.sign(b"payload")
    key = provider.public_key()

    assert provider.verify(b"payload", signature, key)
    assert not provider.verify(b"payloaD", signature, key)
    assert not provider.verify(b"payload", signature, public_key("dev-root"))
    assert not provider.verify(b"payload", signature[:-1], key)
    assert not provider.verify(b"payload", signature, key[:-1])


def test_local_server_chain_of_two_certificates(tmp_path: Path) -> None:
    chain = header_of(jws_vector("02-valid-local-server-lease")["jws"])["chain"]
    provider = Ed25519Provider.from_files(
        key_path("dev-local-server.key"), write_chain(tmp_path / "chain.jws", chain)
    )

    assert provider.kid == "srv_01JAB3K9M2N4P6Q8R0S2T4V6W8-1"
    assert provider.chain == tuple(chain)


def test_key_never_reaches_repr_or_dumps(provider: Ed25519Provider) -> None:
    seed = key_path("dev-issuer.key").read_text(encoding="ascii").strip()

    assert seed not in repr(provider) and seed not in str(provider)
    with pytest.raises(TypeError):
        pickle.dumps(provider)
    with pytest.raises(TypeError):
        copy.copy(provider)
    assert not hasattr(provider, "__dict__")


@pytest.mark.parametrize(
    "content", ["not base64!", "QUJD", "", "Iv3p0bHxzmBgyQvEEIQa7y2jGBNeceoMbL3QNRLgM14="]
)
def test_malformed_key_file_is_refused_without_its_content(tmp_path: Path, content: str) -> None:
    key = tmp_path / "key"
    key.write_text(content + "\n", encoding="ascii")

    with pytest.raises(SigningKeyError) as error:
        Ed25519Provider.from_files(key, DEV_CERT)

    assert error.value.__cause__ is None and error.value.__context__ is None
    if content:
        assert content not in str(error.value)


def test_certificate_of_another_key_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SigningKeyError, match="does not certify"):
        Ed25519Provider.from_files(key_path("dev-local-server.key"), DEV_CERT)


@pytest.mark.parametrize(
    "chain",
    [
        [],
        ["a.b.c"],
        [jws_vector("01-valid-lease")["jws"]],  # a lease, not alm-cert+jws
    ],
)
def test_malformed_certificate_file_is_refused(tmp_path: Path, chain: list[str]) -> None:
    with pytest.raises(SigningKeyError):
        Ed25519Provider.from_files(key_path("dev-issuer.key"), write_chain(tmp_path / "c", chain))


def test_missing_file_is_reported_by_path(tmp_path: Path) -> None:
    with pytest.raises(SigningKeyError, match="missing"):
        Ed25519Provider.from_files(tmp_path / "missing", DEV_CERT)
