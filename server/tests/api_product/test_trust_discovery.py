"""GET /api/v1/trust (E02-04) and GET /.well-known/almi-license (E02-05)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client, override_settings

from infra.clock import FrozenClock, use_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from tests.contract import openapi_errors, schema_errors
from tests.vectors import DEV_ISSUER_CERT, key_path

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def root_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(
        b64url_decode(key_path("dev-root.key").read_text().strip())
    )


def part(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":")).encode())


def bundle_file(tmp_path: Path, clock: FrozenClock, **change: Any) -> Path:
    """What almi-keytool export-trust writes, signed by the dev root."""
    pub = key_path("dev-root.pub").read_text().strip()
    claims = {
        "ver": 1,
        "seq": 4,
        "iat": int(clock.now().timestamp()),
        "roots": [{"kid": "dev-root", "alg": "EdDSA", "pub": pub, "status": "active"}],
        "issuers": [DEV_ISSUER_CERT.read_text().strip()],
        "revoked_kids": ["dev-issuer-0"],
    }
    head, body = part({"alg": "EdDSA", "typ": "alm-trust+jws", "kid": "dev-root"}), part(claims)
    token = f"{head}.{body}.{b64url_encode(root_key().sign(f'{head}.{body}'.encode()))}"
    document = {
        "bundle": token,
        **{k: claims[k] for k in ("roots", "issuers", "revoked_kids", "seq")},
    } | change
    path = tmp_path / "trust.json"
    path.write_text(json.dumps(document))
    return path


def roots() -> list[str]:
    return ["dev-root:" + key_path("dev-root.pub").read_text().strip()]


def test_trust_bundle_is_served_after_checking(tmp_path: Path, clock: FrozenClock) -> None:
    with override_settings(
        TRUST_BUNDLE_FILE=str(bundle_file(tmp_path, clock)), TRUST_ROOTS=roots()
    ):
        response = Client().get("/api/v1/trust")
    assert response.status_code == 200, response.content
    body = response.json()
    assert openapi_errors("TrustBundle", body) == []
    assert body["seq"] == 4 and body["revoked_kids"] == ["dev-issuer-0"]
    claims = json.loads(b64url_decode(body["bundle"].split(".")[1]))
    assert schema_errors("trust", claims) == []


@pytest.mark.parametrize("change", [{"seq": 5}, {"revoked_kids": []}])
def test_bundle_with_unsigned_fields_is_not_served(
    tmp_path: Path, clock: FrozenClock, change: dict[str, Any]
) -> None:
    with override_settings(
        TRUST_BUNDLE_FILE=str(bundle_file(tmp_path, clock, **change)), TRUST_ROOTS=roots()
    ):
        response = Client().get("/api/v1/trust")
    assert response.status_code == 503
    assert response.json()["code"] == "maintenance"


def test_bundle_of_another_root_or_none(tmp_path: Path, clock: FrozenClock) -> None:
    other = [
        "dev-root:" + b64url_encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw())
    ]
    with override_settings(TRUST_BUNDLE_FILE=str(bundle_file(tmp_path, clock)), TRUST_ROOTS=other):
        assert Client().get("/api/v1/trust").status_code == 503
    with override_settings(TRUST_BUNDLE_FILE=""):
        assert Client().get("/api/v1/trust").status_code == 503


def test_discovery_central_and_local(tmp_path: Path, clock: FrozenClock) -> None:
    from apps.packages.models import LocalIdentity

    central = Client().get("/.well-known/almi-license").json()
    assert openapi_errors("Discovery", central) == []
    assert central["deployment_mode"] == "central" and "server_id" not in central
    assert central["server_time"] == "2026-11-02T08:15:00Z"
    with override_settings(DEPLOYMENT_MODE="local"):
        LocalIdentity.objects.create(
            server_id="srv_01JABF8Q4W2N8C1R7ZB0Y5K6M3",
            exchange="files",
            public_key="k",
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        local = Client().get("/.well-known/almi-license").json()
    assert (local["deployment_mode"], local["server_id"]) == (
        "local",
        "srv_01JABF8Q4W2N8C1R7ZB0Y5K6M3",
    )
