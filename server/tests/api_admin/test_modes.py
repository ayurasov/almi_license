"""One image, two modes (E09-01): central-only Admin API routes are 404 on a local server."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client, override_settings

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db

CENTRAL_ONLY = [
    ("get", "/api/admin/catalog/metrics"),
    ("post", "/api/admin/catalog/products"),
    ("get", "/api/admin/profiles"),
    ("get", "/api/admin/profiles/alteroffice-desktop.commercial"),
    ("post", "/api/admin/imports"),
    ("get", "/api/admin/article-mappings"),
]


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def console(clock: FrozenClock) -> Console:
    return sign_in("operator", clock)


def call(console: Console, method: str, path: str) -> Any:
    return console.get(path) if method == "get" else console.post(path)


@pytest.mark.parametrize(("method", "path"), CENTRAL_ONLY)
def test_central_only_routes_are_absent_on_a_local_server(
    console: Console, licensed: Any, method: str, path: str
) -> None:
    assert call(console, method, path).status_code != 404
    with override_settings(DEPLOYMENT_MODE="local"):
        assert call(console, method, path).status_code == 404


def test_key_issue_is_central_only(console: Console, licensed: Any) -> None:
    path = f"/api/admin/licenses/{licensed.id}/keys"
    with override_settings(DEPLOYMENT_MODE="local"):
        assert console.post(path).status_code == 404
        assert console.get(f"/api/admin/licenses/{licensed.id}").status_code == 200
        assert console.get("/api/admin/products").status_code == 200
    assert console.post(path).status_code == 201


WIDENING = ["renew", "resume", "lift-block", "settings", "transfer"]


@pytest.mark.parametrize("action", WIDENING)
def test_local_server_cannot_widen_rights(console: Console, licensed: Any, action: str) -> None:
    """Decision of 29.10.2026 (question В3): rights of a local server come in the package only."""
    path = f"/api/admin/licenses/{licensed.id}/{action}"
    with override_settings(DEPLOYMENT_MODE="local"):
        assert console.post(path, {}).status_code == 404


def test_local_domain_refuses_widening_by_any_route(licensed: Any, clock: FrozenClock) -> None:
    """The domain refuses too (rule 2): no other route or command widens the rights."""
    from apps.licensing.domain.management import (
        create_license,
        renew_license,
        set_license_status,
        update_settings,
    )
    from infra.errors import DomainError

    now = clock.now()
    with override_settings(DEPLOYMENT_MODE="local"):
        for call_ in (
            lambda: create_license({}, actor="user:op", now=now),
            lambda: renew_license(
                licensed.id, valid_until=None, support_until=None, limit=99, actor="u", now=now
            ),
            lambda: update_settings(licensed.id, {"limit": 99}, actor="user:op", now=now),
            lambda: set_license_status(licensed.id, "active", reason="", actor="u", now=now),
        ):
            with pytest.raises(DomainError) as refused:
                call_()
            assert refused.value.code == "forbidden"
        suspended = set_license_status(
            licensed.id, "suspended", reason="Проверка", actor="user:op", now=now
        )
        assert suspended.status == "suspended"
    licensed.refresh_from_db()
    assert licensed.limit != 99


def test_local_create_licence_is_forbidden(console: Console, licensed: Any) -> None:
    from apps.catalog.models import Metric

    body = {
        "customer_id": str(licensed.customer_id),
        "product_id": str(licensed.product_id),
        "metric_id": str(Metric.objects.get().id),
        "type": "perpetual",
        "limit": 5,
        "valid_from": "2026-11-01T00:00:00Z",
    }
    with override_settings(DEPLOYMENT_MODE="local"):
        response = console.post("/api/admin/licenses", body)
        assert (response.status_code, response.json()["code"]) == (403, "forbidden")
    assert console.post("/api/admin/licenses", body).status_code == 201


def test_instance_tells_the_mode_without_a_session() -> None:
    assert Client().get("/api/admin/instance").json() == {
        "mode": "central",
        "setup_required": False,
    }
    with override_settings(DEPLOYMENT_MODE="local"):
        local = Client().get("/api/admin/instance").json()
        assert local == {"mode": "local", "setup_required": True}
