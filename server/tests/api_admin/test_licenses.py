"""Admin API: licenses, keys, activations (E01-05…E01-08, E07-04, E07-05)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def console(clock: FrozenClock) -> Console:
    return sign_in("operator", clock)


def url(license_: Any, action: str = "") -> str:
    return f"/api/admin/licenses/{license_.id}" + (f"/{action}" if action else "")


def test_create_and_list_with_filters(console: Console, licensed: Any) -> None:
    from apps.catalog.models import Metric

    body = {
        "customer_id": str(licensed.customer_id),
        "product_id": str(licensed.product_id),
        "metric_id": str(Metric.objects.get().id),
        "type": "perpetual",
        "limit": 5,
        "valid_from": "2026-11-01T00:00:00Z",
    }
    created = console.post("/api/admin/licenses", body)
    assert created.status_code == 201, created.content
    assert created.json()["type"] == "perpetual" and created.json()["rights_version"] == 1

    everything = console.get("/api/admin/licenses").json()
    expiring = console.get("/api/admin/licenses", {"expires_before": "2028-01-01T00:00:00Z"}).json()
    assert everything["count"] == 2
    assert [item["id"] for item in expiring["results"]] == [str(licensed.id)]
    assert expiring["results"][0]["key_masks"] == ["2645-****-****-81ZT"]
    assert expiring["results"][0]["customer_name"] == "ООО «Пример»"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"limit": 0}, "limit"),
        ({"type": "perpetual", "valid_until": "2027-01-01T00:00:00Z"}, "valid_until"),
    ],
)
def test_create_checks_terms(
    console: Console, licensed: Any, change: dict[str, Any], field: str
) -> None:
    from apps.catalog.models import Metric

    body = {
        "customer_id": str(licensed.customer_id),
        "product_id": str(licensed.product_id),
        "metric_id": str(Metric.objects.get().id),
        "type": "subscription",
        "limit": 5,
        "valid_from": "2026-11-01T00:00:00Z",
    } | change
    response = console.post("/api/admin/licenses", body)
    assert response.status_code == 400 and field in response.json()["data"]["fields"]


def test_renew_raises_rights_version_and_is_audited(console: Console, licensed: Any) -> None:
    response = console.post(
        url(licensed, "renew"), {"valid_until": "2028-10-31T20:59:59Z", "limit": 20}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["valid_until"], body["limit"], body["rights_version"]) == (
        "2028-10-31T20:59:59Z",
        20,
        2,
    )
    history = console.get(url(licensed, "history")).json()
    assert history[0]["action"] == "license.renewed" and history[0]["actor"] == "user:user-operator"


def test_suspend_resume_and_revoke_need_a_reason(console: Console, licensed: Any) -> None:
    assert console.post(url(licensed, "suspend"), {"reason": " "}).json()["data"]["fields"] == {
        "reason": ["Укажите причину."]
    }
    assert (
        console.post(url(licensed, "suspend"), {"reason": "Неоплата"}).json()["status"]
        == "suspended"
    )
    assert console.post(url(licensed, "resume"), {"reason": ""}).json()["status"] == "active"
    assert (
        console.post(url(licensed, "revoke"), {"reason": "Расторжение"}).json()["status"]
        == "revoked"
    )

    again = console.post(url(licensed, "resume"), {"reason": ""})
    assert again.status_code == 400  # revocation is final
    actions = [event["action"] for event in console.get(url(licensed, "history")).json()]
    assert actions[:3] == ["license.revoked", "license.resumed", "license.suspended"]


def test_lift_block_puts_the_lease_into_monitor(
    console: Console, licensed: Any, issuer: Any, server_clock: FrozenClock
) -> None:
    from tests.api_product.test_activate import activate, claims_of, request_body

    until = (server_clock.now() + timedelta(days=30)).isoformat()
    response = console.post(
        url(licensed, "lift-block"), {"until": until, "reason": "Оплата в пути"}
    )

    assert response.status_code == 200 and response.json()["rights_version"] == 2
    lease = activate(request_body()).json()["lease"]
    assert claims_of(lease)["policy"]["enforcement"] == "monitor"

    server_clock.advance(timedelta(days=31))
    lease = activate(request_body()).json()["lease"]
    assert claims_of(lease)["policy"]["enforcement"] == "enforce"


def test_settings_and_mode(console: Console, licensed: Any) -> None:
    response = console.patch(
        url(licensed, "settings"), {"limit": 3, "reserve_pct": 10, "enforcement": "monitor"}
    )

    assert response.status_code == 200
    assert (
        response.json()["limit"],
        response.json()["reserve_pct"],
        response.json()["enforcement"],
    ) == (
        3,
        10,
        "monitor",
    )
    bad = console.patch(url(licensed, "settings"), {"reserve_pct": 101})
    assert bad.status_code == 400 and "reserve_pct" in bad.json()["data"]["fields"]


def test_user_limits_go_to_the_lease(
    console: Console, licensed: Any, issuer: Any, server_clock: FrozenClock
) -> None:
    from tests.api_product.test_activate import activate, claims_of, request_body

    response = console.patch(
        url(licensed, "settings"), {"limits": {"named_users": 500, "only_count_active": False}}
    )
    assert response.status_code == 200
    assert response.json()["limits"] == {
        "named_users": 500,
        "active_users": None,
        "only_count_active": False,
    }
    lease = activate(request_body()).json()["lease"]
    assert claims_of(lease)["limits"] == {"named_users": 500, "only_count_active": False}

    for bad in ({"named_users": 0}, {"active_users": "many"}):
        refused = console.patch(url(licensed, "settings"), {"limits": bad})
        assert refused.status_code == 400, bad
    cleared = console.patch(url(licensed, "settings"), {"limits": {}})
    assert cleared.json()["limits"] == {
        "named_users": None,
        "active_users": None,
        "only_count_active": False,
    }


def test_transfer_to_another_customer(console: Console, licensed: Any, clock: FrozenClock) -> None:
    from apps.licensing.models import Customer

    other = Customer.objects.create(name="АО «Новое»", inn="7736207543", created_at=clock.now())

    response = console.post(
        url(licensed, "transfer"), {"customer_id": str(other.id), "reason": "Реорганизация"}
    )

    assert response.status_code == 200 and response.json()["customer_id"] == str(other.id)
    assert response.json()["key_masks"] == ["2645-****-****-81ZT"]  # keys stay


def test_transfer_is_refused_while_seats_are_with_a_local_server(
    console: Console, licensed: Any, clock: FrozenClock
) -> None:
    from apps.licensing.models import Customer
    from apps.packages.models import Allocation, LocalServer

    server = LocalServer.objects.create(
        external_id="srv_01JAB3K9M2N4P6Q8R0S2T4V6W8",
        customer_id=licensed.customer_id,
        name="ЛС",
        created_at=clock.now(),
    )
    Allocation.objects.create(local_server=server, license_id=licensed.id, seats=5)
    other = Customer.objects.create(name="АО «Новое»", inn="7736207543", created_at=clock.now())

    response = console.post(
        url(licensed, "transfer"), {"customer_id": str(other.id), "reason": "Реорганизация"}
    )

    assert response.status_code == 400
    assert "локальному серверу" in response.json()["data"]["fields"]["customer_id"][0]


def test_issued_key_is_shown_once_and_activates(
    console: Console, licensed: Any, issuer: Any, server_clock: FrozenClock
) -> None:
    import re

    from apps.licensing.domain import key_hash
    from apps.licensing.models import LicenseKey
    from tests.api_product.test_activate import activate, request_body

    response = console.post(url(licensed, "keys"))

    assert response.status_code == 201
    key = response.json()["key"]
    assert re.fullmatch(
        r"4526-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}", key
    )  # week 45 of 2026
    assert response.json()["key_mask"] == f"{key[:4]}-****-****-{key[-4:]}"
    assert LicenseKey.objects.filter(key_hash=key_hash(key)).exists()
    assert key not in str(console.get(url(licensed)).json())
    assert key not in str(console.get(url(licensed, "history")).json())
    assert activate(request_body(license_key=key)).status_code == 201


def test_usage_activations_and_release(console: Console, licensed: Any, issuer: Any) -> None:
    from tests.api_product.test_activate import activate, request_body
    from tests.api_product.test_check import check, check_body

    first = activate(request_body()).json()["activation_id"]
    activate(request_body(instance_id="00000000-0000-4000-8000-000000000002"))

    usage = console.get(url(licensed, "usage")).json()
    assert (usage["active"], usage["by_version"]) == (2, {"3.2.0": 2})
    listed = console.get(
        "/api/admin/activations", {"license_id": str(licensed.id), "search": first}
    ).json()
    assert [item["activation_id"] for item in listed["results"]] == [first]

    assert (
        console.post(f"/api/admin/activations/{first}/release", {"reason": ""}).status_code == 400
    )
    released = console.post(
        f"/api/admin/activations/{first}/release", {"reason": "Списан компьютер"}
    )
    assert released.status_code == 200 and released.json()["status"] == "released"
    assert console.get(url(licensed, "usage")).json()["active"] == 1
    gone = check(first, check_body())
    assert gone.status_code == 410


def test_products_for_selects(console: Console, licensed: Any) -> None:
    products = console.get("/api/admin/products").json()
    assert [(p["code"], [e["code"] for e in p["editions"]]) for p in products] == [
        ("alteroffice-desktop", ["standard"])
    ]


def test_viewer_cannot_manage_licenses(clock: FrozenClock, licensed: Any) -> None:
    viewer = sign_in("customer_viewer", clock)
    assert viewer.get("/api/admin/licenses").status_code == 400
    assert viewer.post(url(licensed, "revoke"), {"reason": "x"}).status_code == 400


def test_dates_are_utc(console: Console, licensed: Any) -> None:
    body = console.get(url(licensed)).json()
    assert datetime.fromisoformat(body["valid_from"]).tzinfo == UTC
