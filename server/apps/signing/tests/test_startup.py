"""The signing key is read at startup from SIGNING_KEY_FILE and SIGNING_CERT_FILE (E02-02)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.signing.apps import configure_signing
from apps.signing.domain import SigningUnavailable, current_provider, install_provider
from tests.vectors import DEV_ISSUER_CERT as DEV_CERT
from tests.vectors import key_path


@pytest.fixture(autouse=True)
def no_provider() -> Iterator[None]:
    install_provider(None)
    yield
    install_provider(None)


def test_both_files_install_the_provider() -> None:
    configure_signing(str(key_path("dev-issuer.key")), str(DEV_CERT), required=True)
    assert current_provider().kid == "dev-issuer-1"


def test_nothing_configured_is_allowed_outside_production() -> None:
    configure_signing("", "", required=False)
    with pytest.raises(SigningUnavailable):
        current_provider()


@pytest.mark.parametrize(
    ("key", "cert", "required"),
    [("", "", True), ("key", "", False), ("", "cert", False)],
)
def test_incomplete_configuration_stops_the_server(key: str, cert: str, required: bool) -> None:
    with pytest.raises(ImproperlyConfigured, match="SIGNING_"):
        configure_signing(key, cert, required=required)


def test_unreadable_key_stops_the_server(tmp_path: Path) -> None:
    (tmp_path / "key").write_text("garbage\n", encoding="ascii")
    with pytest.raises(ImproperlyConfigured, match="SIGNING_KEY_FILE"):
        configure_signing(str(tmp_path / "key"), str(DEV_CERT), required=True)
