"""Admin API: console users managed by an ALMI administrator (E07-09)."""

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
def admin(clock: FrozenClock) -> Console:
    return sign_in("admin", clock)


def password_sign_in(username: str, password: str) -> Client:
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/admin/session").cookies["csrftoken"].value
    response = client.post(
        "/api/admin/session",
        {"username": username, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200, response.content
    # A generated password is temporary: the user changes it first (question 31).
    changed = client.post(
        "/api/admin/session/password",
        {"current_password": password, "new_password": "Ветер-над-Волгой-2026"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert changed.status_code == 200, changed.content
    return client


def test_create_block_role_and_reset(admin: Console) -> None:
    from apps.audit.domain import events_for, verify_chain

    created = admin.post("/api/admin/accounts", {"username": "ivanova", "role": "operator"})
    assert created.status_code == 201, created.content
    first = created.json()["password"]
    assert len(first) == 20
    assert created.json()["account"] == {
        "username": "ivanova",
        "role": "operator",
        "active": True,
        "locked_until": None,
        "last_login": None,
        "created_at": created.json()["account"]["created_at"],
        "customer_id": None,
    }
    session = password_sign_in("ivanova", first)
    assert session.get("/api/admin/customers").status_code == 200
    assert session.get("/api/admin/accounts").status_code == 403

    blocked = admin.patch("/api/admin/accounts/ivanova", {"active": False})
    assert blocked.json()["active"] is False
    assert session.get("/api/admin/customers").status_code == 401

    admin.patch("/api/admin/accounts/ivanova", {"active": True, "role": "admin"})
    reset = admin.post("/api/admin/accounts/ivanova/password")
    second = reset.json()["password"]
    assert second != first
    assert password_sign_in("ivanova", second).get("/api/admin/accounts").status_code == 200

    names = [u["username"] for u in admin.get("/api/admin/accounts").json()]
    assert names == ["ivanova", "user-admin"]
    assert [e["action"] for e in reversed(events_for("user", "ivanova"))] == [
        "iam.account_created",
        "iam.login",
        "iam.password_changed",
        "iam.blocked",
        "iam.role_changed",
        "iam.unblocked",
        "iam.password_reset",
        "iam.login",
        "iam.password_changed",
    ]
    for event in events_for("user", "ivanova"):
        assert first not in str(event) and second not in str(event)
    assert verify_chain()


def test_reset_lifts_the_lockout(admin: Console, clock: FrozenClock) -> None:
    from apps.iam.domain import MAX_FAILURES

    admin.post("/api/admin/accounts", {"username": "petrov", "role": "operator"})
    client = Client()
    for _ in range(MAX_FAILURES):
        client.post(
            "/api/admin/session",
            {"username": "petrov", "password": "wrong"},
            content_type="application/json",
        )
    assert admin.get("/api/admin/accounts").json()[0]["locked_until"] is not None
    password = admin.post("/api/admin/accounts/petrov/password").json()["password"]
    assert admin.get("/api/admin/accounts").json()[0]["locked_until"] is None
    password_sign_in("petrov", password)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"username": "Bad Name", "role": "operator"}, "username"),
        ({"username": "user-admin", "role": "operator"}, "username"),
        ({"username": "viewer", "role": "customer_viewer"}, "customer_id"),
    ],
)
def test_create_validation(admin: Console, body: dict[str, Any], field: str) -> None:
    response = admin.post("/api/admin/accounts", body)
    assert response.status_code == 400
    assert field in response.json()["data"]["fields"]


def test_admin_cannot_change_themselves(admin: Console) -> None:
    response = admin.patch("/api/admin/accounts/user-admin", {"active": False})
    assert response.status_code == 400
    assert "username" in response.json()["data"]["fields"]
    assert admin.post("/api/admin/accounts/user-admin/password").status_code == 400
    assert admin.patch("/api/admin/accounts/nobody", {"active": False}).status_code == 404


def test_operator_has_no_access(clock: FrozenClock) -> None:
    operator = sign_in("operator", clock)
    assert operator.get("/api/admin/accounts").status_code == 403
    assert (
        operator.post("/api/admin/accounts", {"username": "x1", "role": "admin"}).status_code == 403
    )
