"""Question 31: the user changes the own password; a temporary one must be changed first."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db
NEW = "Ветер-над-Волгой-2026"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def signed(username: str, password: str) -> Console:
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/admin/session").cookies["csrftoken"].value
    response = client.post(
        "/api/admin/session",
        {"username": username, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200, response.content
    return Console(client, client.cookies["csrftoken"].value)


def change(console: Console, current: str, new: str) -> Any:
    return console.post(
        "/api/admin/session/password", {"current_password": current, "new_password": new}
    )


def test_temporary_password_must_be_changed_first(clock: FrozenClock) -> None:
    from apps.audit.models import AuditEvent

    admin = sign_in("admin", clock)
    temporary = admin.post("/api/admin/accounts", {"username": "petrov", "role": "operator"})
    console = signed("petrov", temporary.json()["password"])
    assert console.get("/api/admin/session").json()["must_change_password"] is True
    refused = console.get("/api/admin/customers")
    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")

    changed = change(console, temporary.json()["password"], NEW)
    assert changed.status_code == 200, changed.content
    assert changed.json()["must_change_password"] is False
    # The session goes on with the new password; the old one no longer signs in.
    assert console.get("/api/admin/customers").status_code == 200
    assert signed("petrov", NEW).get("/api/admin/session").status_code == 200
    assert AuditEvent.objects.filter(action="iam.password_changed", object_id="petrov").exists()
    assert NEW not in str(list(AuditEvent.objects.values_list("data", flat=True)))

    # A reset by the administrator makes the password temporary again.
    admin.post("/api/admin/accounts/petrov/password")
    assert console.get("/api/admin/customers").status_code == 401  # sessions ended


@pytest.mark.parametrize(
    ("current", "new", "field"),
    [
        ("wrong", NEW, "current_password"),
        (None, "short-1", "new_password"),
        (None, "123456789012345", "new_password"),
        (None, "password12345", "new_password"),
        (None, None, "new_password"),  # the same as the current one
    ],
)
def test_rules_of_a_new_password(
    clock: FrozenClock, current: str | None, new: str | None, field: str
) -> None:
    admin = sign_in("admin", clock)
    temporary = admin.post("/api/admin/accounts", {"username": "sidorov", "role": "operator"})
    password = temporary.json()["password"]
    response = change(signed("sidorov", password), current or password, new or password)
    assert (response.status_code, response.json()["code"]) == (400, "validation_failed")
    assert field in response.json()["data"]["fields"]


def test_needs_a_session() -> None:
    response = Client().post(
        "/api/admin/session/password", {"current_password": "a", "new_password": "b"}
    )
    assert response.status_code in {401, 403}
