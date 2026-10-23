"""issue_jws: compact JWS with the header of section 6.1 of document 2."""

import json
from typing import Any

from infra.crypto.encoding import b64url_encode
from infra.crypto.provider import CryptoProvider

ALG = "EdDSA"
# contracts/schemas/jws-header.schema.json, property typ
TYPES = frozenset(
    {
        "alm-lease+jws",
        "alm-package+jws",
        "alm-cert+jws",
        "alm-receipt+jws",
        "alm-trust+jws",
        "alm-req+jws",
        "alm-lic+jws",
        "alm-usage+jws",
    }
)


class SigningUnavailable(RuntimeError):
    """No issuer key is configured (SIGNING_KEY_FILE and SIGNING_CERT_FILE)."""


_provider: CryptoProvider | None = None


def install_provider(provider: CryptoProvider | None) -> None:
    global _provider
    _provider = provider


def current_provider() -> CryptoProvider:
    if _provider is None:
        raise SigningUnavailable("signing key is not configured")
    return _provider


def _check_keys(value: Any) -> None:
    """json.dumps would turn 1 into "1" silently; object keys must already be strings."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"object key {key!r} is not a string")
            _check_keys(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _check_keys(item)


def canonical_json(value: Any) -> bytes:
    """Sorted keys, no spaces, UTF-8 without escapes; NaN, infinities and non-JSON types fail."""
    _check_keys(value)
    try:
        text = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except TypeError as error:
        raise ValueError(f"not JSON-serialisable: {error}") from None
    return text.encode("utf-8")


def issue_jws(typ: str, claims: dict[str, Any]) -> str:
    if typ not in TYPES:
        raise ValueError(f"unknown JWS typ {typ!r}")
    provider = current_provider()
    header = {"alg": ALG, "typ": typ, "kid": provider.kid, "chain": list(provider.chain)}
    signing_input = (
        f"{b64url_encode(canonical_json(header))}.{b64url_encode(canonical_json(claims))}"
    )
    signature = provider.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{b64url_encode(signature)}"
