"""E07-08: a customer administrator sees only the licences of its customer and changes nothing."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def other(licensed: Any, clock: FrozenClock) -> Any:
    """A licence of another customer."""
    from apps.licensing.models import Customer, License

    customer = Customer.objects.create(name="АО «Другое»", inn="7736207543", created_at=clock.now())
    return License.objects.create(
        customer=customer,
        product=licensed.product,
        metric=licensed.metric,
        type="subscription",
        limit=5,
        valid_from=clock.now(),
        status="active",
        created_at=clock.now(),
        updated_at=clock.now(),
    )


def viewer(admin: Console, customer_id: Any, username: str = "client-admin") -> Console:
    created = admin.post(
        "/api/admin/accounts",
        {"username": username, "role": "customer_viewer", "customer_id": str(customer_id)},
    )
    assert created.status_code == 201, created.content
    assert created.json()["account"]["customer_id"] == str(customer_id)
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/admin/session").cookies["csrftoken"].value
    signed = client.post(
        "/api/admin/session",
        {"username": username, "password": created.json()["password"]},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert signed.status_code == 200
    assert signed.json() == {
        "username": username,
        "role": "customer_viewer",
        "customer_id": str(customer_id),
        "must_change_password": True,
    }
    changed = client.post(
        "/api/admin/session/password",
        {"current_password": created.json()["password"], "new_password": "Ветер-над-Волгой-2026"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert changed.status_code == 200, changed.content
    return Console(client, client.cookies["csrftoken"].value)


def test_sees_only_its_licences(licensed: Any, other: Any, clock: FrozenClock) -> None:
    console = viewer(sign_in("admin", clock), licensed.customer_id)

    page = console.get("/api/admin/licenses").json()
    assert [item["id"] for item in page["results"]] == [str(licensed.id)]
    # A filter by another customer does not widen the view.
    forced = console.get("/api/admin/licenses", {"customer_id": str(other.customer_id)}).json()
    assert [item["id"] for item in forced["results"]] == [str(licensed.id)]

    assert console.get(f"/api/admin/licenses/{licensed.id}").status_code == 200
    assert console.get(f"/api/admin/licenses/{licensed.id}/usage").status_code == 200
    assert console.get(f"/api/admin/licenses/{licensed.id}/history").status_code == 200
    for path in ("", "/usage", "/history"):
        # Another customer's licence is not disclosed: as if it did not exist.
        foreign = console.get(f"/api/admin/licenses/{other.id}{path}")
        assert (foreign.status_code, foreign.json()["code"]) == (404, "not_found")

    stats = console.get("/api/admin/stats", {"customer_id": str(other.customer_id)}).json()
    assert [row["license_id"] for row in stats["rows"]] == [str(licensed.id)]
    assert console.get("/api/admin/stats/export").status_code == 200

    activations = console.get("/api/admin/activations", {"license_id": str(licensed.id)})
    assert activations.status_code == 200
    assert console.get("/api/admin/activations").status_code == 400
    assert console.get("/api/admin/activations", {"license_id": str(other.id)}).status_code == 404
    assert console.get("/api/admin/products").status_code == 200


def test_changes_nothing(licensed: Any, clock: FrozenClock) -> None:
    console = viewer(sign_in("admin", clock), licensed.customer_id)
    base = f"/api/admin/licenses/{licensed.id}"
    refused = [
        console.post(f"{base}/suspend", {"reason": "x"}),
        console.post(f"{base}/keys"),
        console.patch(f"{base}/settings", {"limit": 1}),
        console.post("/api/admin/licenses", {}),
        console.post("/api/admin/customers", {"name": "x"}),
    ]
    assert {(r.status_code, r.json()["code"]) for r in refused} == {(403, "forbidden")}
    for path in ("/api/admin/customers", "/api/admin/accounts", "/api/admin/local-servers"):
        assert console.get(path).status_code == 403, path
    licensed.refresh_from_db()
    assert licensed.status == "active"


def test_binding_is_checked_and_audited(licensed: Any, other: Any, clock: FrozenClock) -> None:
    from apps.audit.models import AuditEvent

    admin = sign_in("admin", clock)
    missing = admin.post("/api/admin/accounts", {"username": "c1", "role": "customer_viewer"})
    assert missing.status_code == 400 and "customer_id" in missing.json()["data"]["fields"]
    unknown = admin.post(
        "/api/admin/accounts",
        {
            "username": "c2",
            "role": "customer_viewer",
            "customer_id": "00000000-0000-4000-8000-000000000000",
        },
    )
    assert unknown.status_code == 400
    viewer(admin, licensed.customer_id, "c3")
    moved = admin.patch("/api/admin/accounts/c3", {"customer_id": str(other.customer_id)})
    assert moved.json()["customer_id"] == str(other.customer_id)
    staff = admin.patch("/api/admin/accounts/c3", {"role": "operator"})
    assert staff.json()["customer_id"] is None
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"iam.account_created", "iam.customer_changed", "iam.role_changed"} <= actions
