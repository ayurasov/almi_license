"""Admin API: catalog and versioned policy profiles (E01-02, E01-03, E07-06)."""

from collections.abc import Iterator
from typing import Any

import pytest

from conftest import POLICY
from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db

PROFILE = "/api/admin/profiles/alteroffice-desktop.commercial"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def console(clock: FrozenClock) -> Console:
    return sign_in("operator", clock)


def fields(response: Any) -> dict[str, list[str]]:
    assert response.status_code == 400, response.content
    assert response["Content-Type"] == "application/problem+json"
    result: dict[str, list[str]] = response.json()["data"]["fields"]
    return result


def test_product_with_capabilities_and_editions(console: Console, licensed: Any) -> None:
    from apps.audit.domain import verify_chain
    from apps.catalog.models import Metric

    metric = console.post(
        "/api/admin/catalog/metrics", {"code": "server_core", "name": {"ru": "Ядро"}}
    )
    assert metric.status_code == 201
    assert {m["code"] for m in console.get("/api/admin/catalog/metrics").json()} == {
        Metric.objects.exclude(code="server_core").get().code,
        "server_core",
    }
    created = console.post(
        "/api/admin/catalog/products",
        {
            "code": "alteroffice-server",
            "name": {"ru": "Сервер"},
            "subject_type": "server_instance",
            "default_metric_id": metric.json()["id"],
        },
    )
    assert created.status_code == 201, created.content
    base = f"/api/admin/catalog/products/{created.json()['id']}"
    for code in ("view", "app:planner"):
        assert console.post(f"{base}/capabilities", {"code": code}).status_code == 201
    edition = console.post(f"{base}/editions", {"code": "standard", "base_capabilities": ["view"]})
    assert edition.json()["editions"] == [
        {
            "id": edition.json()["editions"][0]["id"],
            "code": "standard",
            "name": {},
            "base_capabilities": ["view"],
        }
    ]
    deprecated = console.patch(f"{base}/capabilities/app:planner", {"status": "deprecated"})
    assert {c["code"]: c["status"] for c in deprecated.json()["capabilities"]} == {
        "app:planner": "deprecated",
        "view": "active",
    }
    archived = console.patch(base, {"status": "deprecated"})
    assert archived.json()["status"] == "deprecated"
    assert console.get(base).json()["code"] == "alteroffice-server"
    assert verify_chain()


def test_catalog_rejects_bad_codes(console: Console, licensed: Any) -> None:
    product = f"/api/admin/catalog/products/{licensed.product_id}"
    assert "code" in fields(console.post(f"{product}/capabilities", {"code": "Bad Code"}))
    assert "code" in fields(console.post(f"{product}/capabilities", {"code": "view"}))
    assert "base_capabilities" in fields(
        console.post(f"{product}/editions", {"code": "pro", "base_capabilities": ["missing"]})
    )
    assert "default_profile_code" in fields(console.patch(product, {"default_profile_code": "x.y"}))
    duplicate = console.post(
        "/api/admin/catalog/products",
        {
            "code": licensed.product.code,
            "name": {"ru": "Дубль"},
            "subject_type": "device",
            "default_metric_id": str(licensed.metric_id),
        },
    )
    assert "code" in fields(duplicate)
    missing = console.get("/api/admin/catalog/products/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_profile_change_is_a_new_version(console: Console, licensed: Any) -> None:
    from apps.audit.domain import events_for

    assert [p["version"] for p in console.get("/api/admin/profiles").json()] == [3]
    changed = {**POLICY, "grace_days": 21}
    saved = console.post(PROFILE, {"params": changed})
    assert saved.status_code == 200
    assert saved.json()["version"] == 4
    again = console.post(PROFILE, {"params": changed})
    assert again.json()["version"] == 4
    versions = console.get(PROFILE).json()
    assert [(v["version"], v["params"]["grace_days"]) for v in versions] == [(4, 21), (3, 14)]
    assert [e["action"] for e in events_for("profile", "alteroffice-desktop.commercial")] == [
        "catalog.profile_version"
    ]
    created = console.post("/api/admin/profiles/alteroffice-desktop.trial", {"params": POLICY})
    assert created.json()["version"] == 1


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"enforcement": "strict"}, "enforcement"),
        ({"grace_days": 366}, "grace_days"),
        ({"grace_days": True}, "grace_days"),
        ({"check_interval_hours": 0}, "check_interval_hours"),
        ({"release_after_days": 6}, "release_after_days"),
        ({"reserve_pct": 101}, "reserve_pct"),
        ({"restricted_caps": "updates"}, "restricted_caps"),
        ({"messages": {"m1": {"text": {"ru": "x"}, "severity": "loud"}}}, "messages"),
        ({"messages": {"m1": {"text": "x"}}}, "messages"),
        ({"messages": {"m1": {"text": {"ru": "{days}"}}}}, "messages"),
        ({"messages": {"m1": {"state": "EXPIRED", "text": {}}}}, "messages"),
    ],
)
def test_profile_validation(
    console: Console, licensed: Any, change: dict[str, Any], field: str
) -> None:
    assert field in fields(console.post(PROFILE, {"params": {**POLICY, **change}}))


def test_profile_accepts_messages_and_the_catalog_fixture(console: Console, licensed: Any) -> None:
    import json
    from pathlib import Path

    from apps.policy.domain import profile_errors

    message = {"state": "NOTICE", "text": {"ru": "Осталось {days_left} до {valid_until}"}}
    saved = console.post(PROFILE, {"params": {**POLICY, "messages": {"notice.banner": message}}})
    assert saved.status_code == 200, saved.content
    fixture = Path(__file__).parents[2] / "apps/catalog/fixtures/catalog-v1.json"
    for item in json.loads(fixture.read_text())["profiles"]:
        assert profile_errors({k: v for k, v in item.items() if k != "code"}) == {}


def test_profile_code_and_unknown_profile(console: Console, licensed: Any) -> None:
    assert "code" in fields(console.post("/api/admin/profiles/nodot", {"params": POLICY}))
    assert console.get("/api/admin/profiles/missing.commercial").status_code == 404


def test_catalog_requires_an_operator(client: Any, licensed: Any) -> None:
    assert client.get("/api/admin/profiles").status_code == 401
    assert client.get("/api/admin/catalog/metrics").status_code == 401
