"""A signed-in console client for Admin API tests."""

from typing import Any

from django.test import Client

from infra.clock import FrozenClock

PASSWORD = "operator-test-password"  # test-only value  # noqa: S105


class Console:
    def __init__(self, client: Client, token: str) -> None:
        self.client = client
        self.token = token

    def get(self, path: str, query: dict[str, str | int] | None = None) -> Any:
        return self.client.get(path, query or {})

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.client.post(
            path, body or {}, content_type="application/json", HTTP_X_CSRFTOKEN=self.token
        )

    def patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.patch(
            path, body, content_type="application/json", HTTP_X_CSRFTOKEN=self.token
        )


def sign_in(role: str, clock: FrozenClock) -> Console:
    """A customer viewer is bound to a customer of its own (not the one of the licensed fixture)."""
    from apps.iam.domain import create_account
    from apps.licensing.models import Customer

    customer = None
    if role == "customer_viewer":
        customer = Customer.objects.create(
            name="ООО «Клиент»", inn="7712345671", created_at=clock.now()
        ).id
    create_account(f"user-{role}", PASSWORD, role, now=clock.now(), customer_id=customer)
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/admin/session").cookies["csrftoken"].value
    response = client.post(
        "/api/admin/session",
        {"username": f"user-{role}", "password": PASSWORD},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    return Console(client, client.cookies["csrftoken"].value)
