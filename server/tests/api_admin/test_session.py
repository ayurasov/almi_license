"""Console sign-in (E07-02): Argon2id, session cookie, CSRF, lockout after 10 failures."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client

from infra.clock import FrozenClock, use_clock

PASSWORD = "operator-test-password"  # test-only value  # noqa: S105
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def operator(clock: FrozenClock) -> Any:
    from apps.iam.domain import create_account

    return create_account("operator", PASSWORD, "operator", now=clock.now())


def csrf_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get("/api/admin/session")
    assert response.status_code == 401
    return client, response.cookies["csrftoken"].value


def login(client: Client, token: str, password: str = PASSWORD, username: str = "operator") -> Any:
    return client.post(
        "/api/admin/session",
        {"username": username, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )


def test_password_is_stored_with_argon2id(operator: Any) -> None:
    from django.contrib.auth.models import User

    assert User.objects.get(username="operator").password.startswith("argon2$argon2id$")


def test_login_session_and_logout(operator: Any) -> None:
    client, token = csrf_client()

    response = login(client, token)

    assert response.status_code == 200, response.content
    assert response.json() == {"username": "operator", "role": "operator", "customer_id": None}
    session_cookie = response.cookies["sessionid"]
    assert session_cookie["httponly"] and session_cookie["samesite"] == "Lax"
    assert client.get("/api/admin/session").json()["username"] == "operator"

    token = client.cookies["csrftoken"].value  # rotated on login
    assert client.delete("/api/admin/session", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert client.get("/api/admin/session").status_code == 401


def test_login_without_csrf_token_is_refused(operator: Any) -> None:
    client, _ = csrf_client()

    response = client.post(
        "/api/admin/session",
        {"username": "operator", "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.parametrize(("username", "password"), [("operator", "wrong"), ("nobody", PASSWORD)])
def test_wrong_credentials_give_one_answer(operator: Any, username: str, password: str) -> None:
    client, token = csrf_client()

    response = login(client, token, password, username)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["user_message"]["ru"] == "Неверный логин или пароль."


def test_lockout_after_ten_failures(operator: Any, server_clock: FrozenClock) -> None:
    from apps.audit.models import AuditEvent

    client, token = csrf_client()
    for _ in range(10):
        assert login(client, token, "wrong").status_code == 400

    locked = login(client, token)  # the right password does not help while locked
    assert locked.status_code == 429 and locked.json()["code"] == "rate_limited"
    assert locked["Retry-After"] == "900"
    assert AuditEvent.objects.filter(action="iam.locked").count() == 1

    server_clock.advance(timedelta(minutes=15))
    assert login(client, token).status_code == 200


def test_success_resets_the_failure_count(operator: Any) -> None:
    client, token = csrf_client()
    for _ in range(9):
        login(client, token, "wrong")
    assert login(client, token).status_code == 200
    token = client.cookies["csrftoken"].value
    for _ in range(9):
        assert login(client, token, "wrong").status_code == 400
    assert login(client, token).status_code == 200


def test_password_never_reaches_the_audit(operator: Any) -> None:
    from apps.audit.models import AuditEvent

    client, token = csrf_client()
    login(client, token, "wrong-secret-value")
    login(client, token)

    data = str(list(AuditEvent.objects.values_list("data", flat=True)))
    assert "wrong-secret-value" not in data and PASSWORD not in data
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert actions == {"iam.account_created", "iam.login_failed", "iam.login"}
