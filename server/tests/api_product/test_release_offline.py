"""Release with a receipt (E03-05, section 5.4) and offline files .alk-req/.alk-lic (E08-01,
section 10 of document 2). Outside the apps package: tables of several modules are checked."""

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from conftest import LICENSE_KEY
from infra.clock import FrozenClock, use_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from tests.api_product.test_activate import INSTANCE, activate, claims_of, code_of, request_body
from tests.contract import openapi_errors, schema_errors
from tests.signed import public_b64, signed_post

pytestmark = pytest.mark.django_db
OFFLINE = "/api/v1/offline/requests"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def device() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def release(activation_id: str, key: Ed25519PrivateKey) -> Any:
    body = {"reason": "uninstall", "client_time": "2026-11-02T09:00:00Z"}
    return signed_post(
        Client(), f"/api/v1/activations/{activation_id}/release", body, key, activation_id
    )


def b64json(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":")).encode())


def alk_req(payload: dict[str, Any], key: Ed25519PrivateKey) -> bytes:
    header = b64json({"alg": "EdDSA", "typ": "alm-req+jws", "kid": "device"})
    body = b64json(payload)
    sig = b64url_encode(key.sign(f"{header}.{body}".encode()))
    return json.dumps(
        {"format": "alk-req", "version": 1, "payload": f"{header}.{body}.{sig}"}
    ).encode()


def offline_payload(
    key: Ed25519PrivateKey, clock: FrozenClock, kind: str = "activate", **extra: Any
) -> dict[str, Any]:
    document = request_body(key)
    document.pop("client_time")
    if kind != "activate":
        document.pop("license_key")
    return {
        "type": kind,
        **document,
        "nonce": b64url_encode(b"n" * 16),
        "created": clock.now().isoformat().replace("+00:00", "Z"),
        **extra,
    }


def upload(content: bytes, name: str = "WS-0451.alk-req") -> Any:
    return Client().post(OFFLINE, {"file": SimpleUploadedFile(name, content)})


def opened(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.content
    document = response.json()
    assert openapi_errors("AlkFile", document) == []
    assert schema_errors("alk-file", document) == []
    header = json.loads(b64url_decode(document["payload"].split(".")[0]))
    assert header["typ"] == "alm-lic+jws"
    claims = claims_of(document["payload"])
    assert schema_errors("alk-lic", claims) == []
    return claims


# E03-05 -------------------------------------------------------------------------------------


def test_release_frees_the_seat_and_repeats_the_receipt(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    from apps.activation.domain import license_usage

    activation_id = activate(request_body(device), device).json()["activation_id"]
    first = release(activation_id, device)
    assert first.status_code == 200, first.content
    assert openapi_errors("ReleaseResponse", first.json()) == []
    receipt = claims_of(first.json()["receipt"])
    assert schema_errors("receipt", receipt) == []
    assert (receipt["type"], receipt["activation_id"]) == ("release", activation_id)
    assert license_usage(licensed.id).active == 0

    again = release(activation_id, device)
    assert again.json() == first.json()
    from apps.activation.models import Activation

    row = Activation.objects.get(external_id=activation_id)
    assert (row.status, row.released_at) == ("released", clock.now())


def test_release_after_operator_release_gives_a_receipt(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    from apps.activation.domain import release_by_operator

    activation_id = activate(request_body(device), device).json()["activation_id"]
    released = release_by_operator(
        activation_id, reason="Перенос", actor="user:op", now=clock.now()
    )
    response = release(activation_id, device)
    assert response.status_code == 200
    assert released.released_at is not None
    assert response.json()["released_at"] == released.released_at.isoformat().replace("+00:00", "Z")


def test_release_needs_the_activation_key(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey
) -> None:
    activation_id = activate(request_body(device), device).json()["activation_id"]
    other = Ed25519PrivateKey.generate()
    assert code_of(release(activation_id, other)) == "signature_invalid"
    assert code_of(release("act_unknown", device)) == "signature_invalid"


# E08-01 -------------------------------------------------------------------------------------


def test_offline_activation_and_repeat(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    from apps.activation.domain import license_usage

    content = alk_req(offline_payload(device, clock), device)
    response = upload(content)
    claims = opened(response)
    assert response["Content-Disposition"] == f'attachment; filename="{INSTANCE}.alk-lic"'
    assert claims["request_nonce"] == b64url_encode(b"n" * 16)
    assert claims["respond_before"] == (clock.now() + timedelta(days=30)).isoformat().replace(
        "+00:00", "Z"
    )
    lease = claims_of(claims["lease"])
    assert schema_errors("lease", lease) == []
    assert lease["sub"] == claims["activation_id"]
    assert lease["subject"]["instance_id"] == INSTANCE

    again = opened(upload(content))
    assert again["activation_id"] == claims["activation_id"]
    assert license_usage(licensed.id).active == 1  # the repeat takes no second seat


def test_offline_renew_and_release(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    activation_id = opened(upload(alk_req(offline_payload(device, clock), device)))["activation_id"]

    renew = opened(
        upload(
            alk_req(offline_payload(device, clock, "renew", activation_id=activation_id), device)
        )
    )
    assert claims_of(renew["lease"])["seq"] == 2

    released = opened(
        upload(
            alk_req(offline_payload(device, clock, "release", activation_id=activation_id), device)
        )
    )
    assert "lease" not in released
    assert claims_of(released["receipt"])["activation_id"] == activation_id

    other = Ed25519PrivateKey.generate()
    stolen = offline_payload(other, clock, "renew", activation_id=activation_id)
    assert code_of(upload(alk_req(stolen, other))) == "signature_invalid"


def test_changed_byte_is_refused(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    container = json.loads(alk_req(offline_payload(device, clock), device))
    header, body, sig = container["payload"].split(".")
    payload = json.loads(b64url_decode(body))
    payload["license_key"] = LICENSE_KEY.replace("8", "9", 1)
    container["payload"] = f"{header}.{b64json(payload)}.{sig}"
    assert code_of(upload(json.dumps(container).encode())) == "signature_invalid"

    flipped = bytearray(b64url_decode(sig))
    flipped[0] ^= 1
    container["payload"] = f"{header}.{body}.{b64url_encode(bytes(flipped))}"
    assert code_of(upload(json.dumps(container).encode())) == "signature_invalid"


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        json.dumps({"format": "alk-lic", "version": 1, "payload": "a.b.c"}).encode(),
        json.dumps({"format": "alk-req", "version": 2, "payload": "a.b.c"}).encode(),
        json.dumps({"format": "alk-req", "version": 1, "payload": "only-one-part"}).encode(),
        b" " * (64 * 1024 + 1),
    ],
)
def test_bad_containers(licensed: Any, issuer: Any, content: bytes) -> None:
    assert code_of(upload(content)) == "invalid_request"


def test_old_request_and_missing_fields(
    licensed: Any, issuer: Any, device: Ed25519PrivateKey, clock: FrozenClock
) -> None:
    old = offline_payload(device, clock)
    old["created"] = (clock.now() - timedelta(days=31)).isoformat()
    assert code_of(upload(alk_req(old, device))) == "invalid_request"

    no_key = offline_payload(device, clock)
    no_key.pop("license_key")
    assert code_of(upload(alk_req(no_key, device))) == "invalid_request"

    wrong_key = offline_payload(
        device, clock, device_pubkey=public_b64(Ed25519PrivateKey.generate())
    )
    assert code_of(upload(alk_req(wrong_key, device))) == "signature_invalid"

    assert Client().post(OFFLINE, {}).status_code == 400
