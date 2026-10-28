"""Admin API: customers (E01-04) — the data behind the reference console screen (E07-03)."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from infra.clock import FrozenClock, use_clock

PASSWORD = "operator-test-password"  # test-only value  # noqa: S105
pytestmark = pytest.mark.django_db
URL = "/api/admin/customers"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def signed_in(role: str, clock: FrozenClock) -> tuple[Client, str]:
    from apps.iam.domain import create_account
    from apps.licensing.models import Customer

    customer = None
    if role == "customer_viewer":
        customer = Customer.objects.create(
            name="ООО «Клиент»", inn="7701234560", created_at=clock.now()
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
    return client, client.cookies["csrftoken"].value


@pytest.fixture
def operator(clock: FrozenClock) -> tuple[Client, str]:
    return signed_in("operator", clock)


def post(session: tuple[Client, str], body: dict[str, Any]) -> Any:
    client, token = session
    return client.post(URL, body, content_type="application/json", HTTP_X_CSRFTOKEN=token)


def patch(session: tuple[Client, str], customer_id: str, body: dict[str, Any]) -> Any:
    client, token = session
    return client.patch(
        f"{URL}/{customer_id}", body, content_type="application/json", HTTP_X_CSRFTOKEN=token
    )


def test_create_get_update(operator: tuple[Client, str], clock: FrozenClock) -> None:
    from apps.audit.models import AuditEvent

    created = post(operator, {"name": "ООО «Ромашка»", "inn": "7707083893"})

    assert created.status_code == 201, created.content
    customer = created.json()
    assert customer | {"id": "x"} == {
        "id": "x",
        "name": "ООО «Ромашка»",
        "inn": "7707083893",
        "external_id": "",
        "status": "active",
        "created_at": "2026-11-02T08:15:00Z",
    }
    client, _ = operator
    assert client.get(f"{URL}/{customer['id']}").json() == customer

    updated = patch(operator, customer["id"], {"name": "АО «Ромашка»", "status": "archived"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "АО «Ромашка»" and updated.json()["status"] == "archived"
    assert list(AuditEvent.objects.order_by("seq").values_list("action", flat=True))[-2:] == [
        "customer.created",
        "customer.updated",
    ]


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"name": "", "inn": "7707083893"}, "name", "Укажите наименование."),
        (
            {"name": "А", "inn": "7707083894"},
            "inn",
            "Неверный ИНН: 10 или 12 цифр с верной контрольной суммой.",
        ),
        (
            {"name": "А", "inn": "7707083893", "status": "deleted"},
            "status",
            "Недопустимое значение.",
        ),
    ],
)
def test_field_errors(
    operator: tuple[Client, str], body: dict[str, Any], field: str, message: str
) -> None:
    response = post(operator, body)

    assert response.status_code == 400
    problem = response.json()
    assert problem["code"] == "validation_failed"
    assert problem["data"]["fields"][field] == [message]


def test_inn_and_external_id_are_unique(operator: tuple[Client, str]) -> None:
    assert (
        post(operator, {"name": "А", "inn": "7707083893", "external_id": "lk-1"}).status_code == 201
    )

    same_inn = post(operator, {"name": "Б", "inn": "7707083893"})
    same_ref = post(operator, {"name": "В", "inn": "7736207543", "external_id": "lk-1"})

    assert same_inn.json()["data"]["fields"] == {"inn": ["Заказчик с таким ИНН уже есть."]}
    assert same_ref.json()["data"]["fields"] == {
        "external_id": ["Заказчик с таким идентификатором ЛК уже есть."]
    }


def test_list_pagination_sorting_and_filters(operator: tuple[Client, str]) -> None:
    names = ["Альфа", "Бета", "Гамма", "Дельта", "Эпсилон"]
    inns = ["7707083893", "7736207543", "500100732259", "773370857141", "7728168971"]
    for name, inn in zip(names, inns, strict=True):
        post(operator, {"name": f"ООО «{name}»", "inn": inn})
    client, _ = operator
    first = post(operator, {"name": "АО «Архив»"}).json()
    patch(operator, first["id"], {"status": "archived"})

    query: dict[str, str | int] = {"page": 2, "page_size": 2, "ordering": "-name"}
    page = client.get(URL, query).json()
    by_name = client.get(URL, {"name": "гам"}).json()
    by_inn = client.get(URL, {"inn": "7736"}).json()
    archived = client.get(URL, {"status": "archived"}).json()

    assert page["count"] == 6
    # -name: Эпсилон, Дельта | Гамма, Бета | Альфа, АО «Архив»
    assert [c["name"] for c in page["results"]] == ["ООО «Гамма»", "ООО «Бета»"]
    assert [c["name"] for c in by_name["results"]] == ["ООО «Гамма»"]
    assert [c["inn"] for c in by_inn["results"]] == ["7736207543"]
    assert [c["name"] for c in archived["results"]] == ["АО «Архив»"]


@pytest.mark.parametrize(
    "query", [{"ordering": "password"}, {"page_size": 1000}, {"status": "x"}, {"page": 0}]
)
def test_bad_list_parameters(operator: tuple[Client, str], query: dict[str, str | int]) -> None:
    client, _ = operator
    response = client.get(URL, query)
    assert response.status_code == 400 and response.json()["code"] == "validation_failed"


def test_requires_a_session() -> None:
    response = Client().get(URL)
    assert response.status_code == 401 and response.json()["code"] == "not_authenticated"


def test_customer_viewer_cannot_manage_customers(clock: FrozenClock) -> None:
    client, _ = signed_in("customer_viewer", clock)
    response = client.get(URL)
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_writes_need_the_csrf_token(operator: tuple[Client, str]) -> None:
    client, _ = operator
    response = client.post(URL, {"name": "А"}, content_type="application/json")
    assert response.status_code == 403 and "CSRF" in response.json()["detail"]


def test_unknown_customer(operator: tuple[Client, str]) -> None:
    client, _ = operator
    response = client.get(f"{URL}/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


def test_admin_schema_describes_customers(operator: tuple[Client, str]) -> None:
    client, _ = operator
    schema = client.get("/api/admin/schema", {"format": "json"}).json()
    assert "/api/admin/customers" in schema["paths"]
    assert "/api/admin/customers/{customer_id}" in schema["paths"]
    assert "/api/v1/activations" not in schema["paths"]
