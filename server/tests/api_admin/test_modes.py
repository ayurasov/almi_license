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


def test_instance_tells_the_mode_without_a_session() -> None:
    assert Client().get("/api/admin/instance").json() == {"mode": "central"}
    with override_settings(DEPLOYMENT_MODE="local"):
        assert Client().get("/api/admin/instance").json() == {"mode": "local"}
