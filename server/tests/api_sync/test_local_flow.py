"""Central and local server together (E09-01…E09-04): wizard, registration online and by file,
package import, leases signed by the local server key within the seats of the package.

One test database plays both servers: after the registration the central rows of the packages
module are deleted, as a local server has none of them in its own database.
"""

import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.test import Client, override_settings

from infra.clock import FrozenClock, use_clock
from infra.http import HttpResponse, install_transport
from tests.api_product.test_activate import activate, claims_of, request_body
from tests.vectors import key_path

pytestmark = pytest.mark.django_db
CENTRAL = "https://central.test"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def central_transport() -> Iterator[list[str]]:
    """The central server of the test: requests of the local server go to the same Django."""
    seen: list[str] = []

    def transport(method: str, url: str, body: bytes, headers: dict[str, str]) -> HttpResponse:
        path = url.removeprefix(CENTRAL)
        seen.append(f"{method} {path}")
        with override_settings(DEPLOYMENT_MODE="central"):
            reply = Client().generic(
                method,
                path,
                body,
                content_type="application/json",
                HTTP_ALMI_SIGNATURE=headers["ALMI-Signature"],
            )
        return HttpResponse(reply.status_code, reply.content)

    install_transport(transport)
    yield seen
    install_transport(None)


@pytest.fixture
def local_settings(tmp_path: Path) -> Iterator[None]:
    root = key_path("dev-root.pub").read_text(encoding="ascii").strip()
    with override_settings(
        DEPLOYMENT_MODE="local",
        LOCAL_SERVER_KEY_FILE=str(tmp_path / "server.key"),
        TRUST_ROOTS=[f"dev-root:{root}"],
    ):
        yield


def central_code(licensed: Any, clock: FrozenClock, seats: int = 4) -> str:
    from apps.packages.domain import create_server

    with override_settings(DEPLOYMENT_MODE="central"):
        return create_server(
            licensed.customer_id, "ЦОД", {str(licensed.id): seats}, actor="user:op", now=clock.now()
        ).code


def forget_central() -> None:
    from apps.packages.models import Allocation, LocalServer, Package

    Allocation.objects.all().delete()
    Package.objects.all().delete()
    LocalServer.objects.all().delete()


def verify_lease(token: str) -> Any:
    from apps.signing.domain import verify_signed
    from infra.clock import current_clock
    from tests.vectors import public_key

    return verify_signed(
        token,
        typ="alm-lease+jws",
        roots={"dev-root": public_key("dev-root")},
        now=current_clock().now(),
    )


def test_online_registration_and_local_leases(
    licensed: Any,
    issuer: Any,
    clock: FrozenClock,
    central_transport: list[str],
    local_settings: None,
    tmp_path: Path,
) -> None:
    from apps.packages.domain import local_status, setup, sync_package

    licensed.limits = {"named_users": 50, "only_count_active": False}
    licensed.save()
    code = central_code(licensed, clock)
    result = setup(registration_code=code, central_url=CENTRAL, actor="user:admin", now=clock.now())
    assert central_transport == ["POST /api/sync/v1/servers/register"]
    assert result.request_file is None
    status = local_status()
    assert (status.registered, status.package_seq) == (True, 1)
    assert oct((tmp_path / "server.key").stat().st_mode & 0o777) == "0o600"
    assert sync_package(now=clock.now()) is None  # 204: nothing new
    assert central_transport[-1].startswith("GET /api/sync/v1/servers/")
    forget_central()

    first = activate(request_body())
    assert first.status_code == 201, first.content
    verified = verify_lease(first.json()["lease"])
    assert verified.leaf is not None and verified.leaf["role"] == "local_server"
    assert verified.leaf["kid"] == status.server_id
    lease = verified.claims
    assert lease["lic"]["customer"]["id"] == str(licensed.customer_id)
    assert lease["limits"] == {"named_users": 50, "only_count_active": False}  # via the package
    assert status.package_valid_until is not None
    assert lease["exp"] <= int(status.package_valid_until.timestamp())

    # 4 seats of the package + ceil(4 * 3 %) = 1 reserve seat.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    codes = []
    for n in range(2, 7):
        key = Ed25519PrivateKey.generate()
        instance = f"8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c{n:02}"
        codes.append(activate(request_body(key, instance_id=instance), key).status_code)
    assert codes == [201, 201, 201, 201, 409]


def test_files_mode_registration_and_package_upload(
    licensed: Any, issuer: Any, clock: FrozenClock, local_settings: None
) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.packages.domain import register_from_file, setup
    from tests.api_admin.session import sign_in

    code = central_code(licensed, clock, seats=2)
    result = setup(registration_code=code, central_url=None, actor="user:admin", now=clock.now())
    assert result.request_file is not None and result.request_file["format"] == "alk-req"
    assert code in json.dumps(claims_of(result.request_file["payload"]))

    with override_settings(DEPLOYMENT_MODE="central"):
        _, package = register_from_file(json.dumps(result.request_file).encode(), now=clock.now())
    forget_central()

    console = sign_in("operator", clock)
    upload = console.client.post(
        "/api/admin/package",
        {"file": SimpleUploadedFile("server.alk", json.dumps(package).encode())},
        HTTP_X_CSRFTOKEN=console.token,
    )
    assert upload.status_code == 200, upload.content
    assert upload.json()["package_seq"] == 1
    again = console.client.post(
        "/api/admin/package",
        {"file": SimpleUploadedFile("server.alk", json.dumps(package).encode())},
        HTTP_X_CSRFTOKEN=console.token,
    )
    assert again.json()["data"]["fields"]["file"] == ["Номер пакета должен быть больше 1."]
    assert activate(request_body()).status_code == 201


def test_package_checks(
    licensed: Any, issuer: Any, clock: FrozenClock, local_settings: None
) -> None:
    from apps.packages.domain import import_package, register_from_file, setup
    from infra.errors import DomainError

    code = central_code(licensed, clock)
    request_file = setup(
        registration_code=code, central_url=None, actor="a", now=clock.now()
    ).request_file
    with override_settings(DEPLOYMENT_MODE="central"):
        _, package = register_from_file(json.dumps(request_file).encode(), now=clock.now())

    head, body, sig = package["payload"].split(".")
    forged = dict(claims_of(package["payload"]), seq=99)
    from infra.crypto.encoding import b64url_encode

    tampered = {**package, "payload": f"{head}.{b64url_encode(json.dumps(forged).encode())}.{sig}"}
    with pytest.raises(DomainError, match="signature_invalid"):
        import_package(tampered, actor="a", now=clock.now())
    other = ["other-root:" + b64url_encode(bytes(32))]
    with override_settings(TRUST_ROOTS=other), pytest.raises(DomainError, match="chain_invalid"):
        import_package(package, actor="a", now=clock.now())
    with pytest.raises(DomainError, match="expired"):
        import_package(package, actor="a", now=clock.now() + timedelta(days=400))
    import_package(package, actor="a", now=clock.now())


def test_wizard_and_mode_endpoints(
    licensed: Any, issuer: Any, clock: FrozenClock, local_settings: None
) -> None:
    from tests.api_admin.session import sign_in

    assert Client().get("/api/admin/instance").json() == {"mode": "local", "setup_required": True}
    admin = sign_in("admin", clock)
    status = admin.get("/api/admin/setup").json()
    assert (status["configured"], status["registered"]) == (False, False)
    reply = admin.post(
        "/api/admin/setup", {"registration_code": "AAAAA-BBBBB", "central_url": "http://x"}
    )
    assert "central_url" in reply.json()["data"]["fields"]
    files = admin.post("/api/admin/setup", {"registration_code": "AAAAA-BBBBB"})
    assert files.status_code == 200
    assert files.json()["request_file"]["format"] == "alk-req"
    assert sign_in("operator", clock).get("/api/admin/setup").status_code == 400
    with override_settings(DEPLOYMENT_MODE="central"):
        assert admin.get("/api/admin/setup").status_code == 404
