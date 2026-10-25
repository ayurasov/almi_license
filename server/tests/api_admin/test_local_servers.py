"""Admin API: local servers — one-time code, seats, registration by file (E09-02)."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from infra.clock import FrozenClock, use_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from tests.api_admin.session import Console, sign_in
from tests.api_sync.local import LocalServerClient, claims

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def console(clock: FrozenClock) -> Console:
    return sign_in("operator", clock)


def server_request(local: LocalServerClient, code: str) -> bytes:
    def part(value: dict[str, Any]) -> str:
        return b64url_encode(json.dumps(value).encode())

    header = part({"alg": "EdDSA", "typ": "alm-req+jws", "kid": local.server_id})
    body = part(
        {
            "type": "server",
            "registration_code": code,
            "server_id": local.server_id,
            "server_pubkey": local.public_key,
            "host_fingerprint": {"machine_id": "m1", "hostname": "h1"},
            "version": "1.0.0",
            "nonce": "n1",
            "created": "2026-11-02T08:00:00Z",
        }
    )
    sig = b64url_encode(local.key.sign(f"{header}.{body}".encode()))
    return json.dumps(
        {"format": "alk-req", "version": 1, "payload": f"{header}.{body}.{sig}"}
    ).encode()


def upload(console: Console, content: bytes) -> Any:
    return console.client.post(
        "/api/admin/local-servers/register-file",
        {"file": SimpleUploadedFile("server.alk-req", content)},
        HTTP_X_CSRFTOKEN=console.token,
    )


def test_create_code_once_and_register_by_file(
    console: Console, licensed: Any, issuer: Any
) -> None:
    from apps.audit.domain import verify_chain

    body = {
        "customer_id": str(licensed.customer_id),
        "name": "ЦОД",
        "allocations": {str(licensed.id): 3},
    }
    created = console.post("/api/admin/local-servers", body)
    assert created.status_code == 201, created.content
    code = created.json()["code"]
    assert created.json()["server"]["registered"] is False
    assert code not in str(console.get("/api/admin/local-servers").json())

    local = LocalServerClient()
    response = upload(console, server_request(local, code))
    assert response.status_code == 200, response.content
    assert response["Content-Disposition"] == f'attachment; filename="{local.server_id}.alk"'
    package = claims(response.json()["payload"])
    assert package["server_id"] == local.server_id
    assert claims(package["trust"]["server_certificate"])["pub"] == local.public_key

    [server] = console.get("/api/admin/local-servers").json()
    assert (server["server_id"], server["registered"], server["status"]) == (
        local.server_id,
        True,
        "active",
    )
    assert verify_chain()


def test_bad_seats_new_code_and_forged_file(console: Console, licensed: Any, issuer: Any) -> None:
    too_many = {
        "customer_id": str(licensed.customer_id),
        "name": "X",
        "allocations": {str(licensed.id): 99},
    }
    assert (
        "allocations" in console.post("/api/admin/local-servers", too_many).json()["data"]["fields"]
    )

    body = too_many | {"allocations": {str(licensed.id): 1}}
    created = console.post("/api/admin/local-servers", body).json()
    fresh = console.post(f"/api/admin/local-servers/{created['server']['id']}/code").json()["code"]
    assert fresh != created["code"]

    local = LocalServerClient()
    assert (
        upload(console, server_request(local, created["code"])).json()["code"] == "invalid_request"
    )
    container = json.loads(server_request(local, fresh))
    head, payload, sig = container["payload"].split(".")
    # Flip one bit of the signature: always a different, invalid signature.
    broken = bytearray(b64url_decode(sig))
    broken[0] ^= 1
    container["payload"] = f"{head}.{payload}.{b64url_encode(bytes(broken))}"
    assert upload(console, json.dumps(container).encode()).json()["code"] == "signature_invalid"

    seats = console.client.put(
        f"/api/admin/local-servers/{created['server']['id']}/allocations",
        {"allocations": {str(licensed.id): 2}},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=console.token,
    )
    assert seats.json()["allocations"] == {str(licensed.id): 2}


def test_package_expiry_warning(
    console: Console, licensed: Any, issuer: Any, server_clock: FrozenClock
) -> None:
    from datetime import timedelta

    body = {
        "customer_id": str(licensed.customer_id),
        "name": "ЦОД",
        "allocations": {str(licensed.id): 3},
    }
    code = console.post("/api/admin/local-servers", body).json()["code"]
    upload(console, server_request(LocalServerClient(), code))
    [server] = console.get("/api/admin/local-servers").json()
    assert server["package_valid_until"] is not None
    assert server["package_expires_soon"] is False
    server_clock.advance(timedelta(days=365 - 30))  # the package is valid 365 days
    [server] = console.get("/api/admin/local-servers").json()
    assert server["package_expires_soon"] is True
