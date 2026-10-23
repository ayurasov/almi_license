from pathlib import Path

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.signing.domain import install_provider
from infra.crypto.ed25519 import Ed25519Provider, SigningKeyError


def configure_signing(key_file: str, cert_file: str, *, required: bool) -> None:
    """Read the issuer key once at startup; a broken configuration stops the server."""
    if not key_file and not cert_file and not required:
        install_provider(None)
        return
    if not key_file or not cert_file:
        raise ImproperlyConfigured("SIGNING_KEY_FILE and SIGNING_CERT_FILE must both be set")
    try:
        install_provider(Ed25519Provider.from_files(Path(key_file), Path(cert_file)))
    except SigningKeyError as error:
        raise ImproperlyConfigured(str(error)) from None


class SigningConfig(AppConfig):
    name = "apps.signing"
    label = "signing"

    def ready(self) -> None:
        configure_signing(
            settings.SIGNING_KEY_FILE,
            settings.SIGNING_CERT_FILE,
            required=settings.SIGNING_REQUIRED,
        )
