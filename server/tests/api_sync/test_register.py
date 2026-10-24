"""Registration of a local server and its package (E09-02; section 13 of document 2)."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.test import override_settings

from infra.clock import FrozenClock, use_clock
from tests.api_sync.local import LocalServerClient, claims, header
from tests.contract import openapi_errors, schema_errors

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def code(licensed: Any, clock: FrozenClock) -> str:
    from apps.packages.domain import create_server

    issued = create_server(
        licensed.customer_id, "Сервер ЦОД", {str(licensed.id): 4}, actor="user:op", now=clock.now()
    )
    return issued.code


def test_registration_gives_certificate_and_package(code: str, licensed: Any, issuer: Any) -> None:
    from apps.licensing.domain import key_hash
    from conftest import LICENSE_KEY

    local = LocalServerClient()
    response = local.register(code)
    assert response.status_code == 200, response.content
    body = response.json()
    assert openapi_errors("ServerRegisterResponse", body) == []

    certificate = claims(body["certificate"])
    assert schema_errors("cert", certificate) == []
    assert header(body["certificate"])["typ"] == "alm-cert+jws"
    assert (certificate["role"], certificate["kid"], certificate["pub"]) == (
        "local_server",
        local.server_id,
        local.public_key,
    )
    assert certificate["scope"] == {
        "server_id": local.server_id,
        "customer_id": str(licensed.customer_id),
        "products": ["alteroffice-desktop"],
        "quotas": {str(licensed.id): 4},
    }

    package = claims(body["package"]["payload"])
    assert body["package"]["format"] == "alk"
    assert header(body["package"]["payload"])["typ"] == "alm-package+jws"
    assert schema_errors("package", package) == []
    assert package["seq"] == 1
    [item] = package["licenses"]
    assert (item["license_id"], item["allocation"], item["product"]) == (
        str(licensed.id),
        4,
        "alteroffice-desktop",
    )
    assert package["keys"][0]["key_hash"] == key_hash(LICENSE_KEY)
    assert LICENSE_KEY not in str(package)
    assert package["trust"]["server_certificate"] == body["certificate"]


def test_repeat_is_idempotent_and_code_is_one_time(code: str, issuer: Any) -> None:
    local = LocalServerClient()
    first = local.register(code).json()
    again = local.register(code)
    assert again.status_code == 200
    assert again.json() == first

    other = LocalServerClient()
    assert other.register(code).json()["code"] == "invalid_request"


def test_bad_registrations(code: str, issuer: Any, clock: FrozenClock) -> None:
    local = LocalServerClient()
    assert local.register("WRONG-CODE").json()["code"] == "invalid_request"
    assert local.register(code, server_id="srv_bad").json()["code"] == "signature_invalid"
    clock.advance(timedelta(days=8))
    assert local.register(code).json()["code"] == "invalid_request"


def test_package_since_seq_and_new_seq_on_change(
    code: str, licensed: Any, issuer: Any, clock: FrozenClock
) -> None:
    from apps.packages.domain import list_servers, set_allocations

    local = LocalServerClient()
    local.register(code)
    assert local.package(since_seq=1).status_code == 204
    full = local.package(since_seq=0)
    assert full.status_code == 200 and claims(full.json()["payload"])["seq"] == 1

    [server] = list_servers()
    set_allocations(server.id, {str(licensed.id): 2}, actor="user:op", now=clock.now())
    newer = local.package(since_seq=1)
    assert claims(newer.json()["payload"])["seq"] == 2
    assert claims(newer.json()["payload"])["licenses"][0]["allocation"] == 2

    stranger = LocalServerClient()
    assert stranger.package().json()["code"] == "signature_invalid"


def test_allocated_seats_leave_the_central_server(
    licensed: Any, issuer: Any, clock: FrozenClock
) -> None:
    from apps.packages.domain import create_server
    from infra.errors import DomainError

    with pytest.raises(DomainError):
        create_server(
            licensed.customer_id, "Много", {str(licensed.id): 11}, actor="user:op", now=clock.now()
        )
    create_server(
        licensed.customer_id, "Все места", {str(licensed.id): 10}, actor="user:op", now=clock.now()
    )

    from tests.api_product.test_activate import activate, code_of, request_body

    assert code_of(activate(request_body())) == "seats_exhausted"


def test_sync_is_absent_on_a_local_server(code: str, issuer: Any) -> None:
    with override_settings(DEPLOYMENT_MODE="local"):
        assert LocalServerClient().register(code).status_code == 404
