"""Admin API error codes of section 16 of document 2 (question 23); Product API codes stay."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import sign_in

pytestmark = pytest.mark.django_db

MISSING = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def code(response: Any) -> tuple[int, str]:
    assert response["Content-Type"] == "application/problem+json"
    return response.status_code, response.json()["code"]


def test_session_rights_objects_and_fields(clock: FrozenClock) -> None:
    assert code(Client().get("/api/admin/licenses")) == (401, "not_authenticated")
    operator = sign_in("operator", clock)
    assert code(operator.get("/api/admin/accounts")) == (403, "forbidden")
    for path in (
        f"/api/admin/licenses/{MISSING}",
        f"/api/admin/customers/{MISSING}",
        f"/api/admin/catalog/products/{MISSING}",
    ):
        assert code(operator.get(path)) == (404, "not_found"), path
    invalid = operator.post("/api/admin/customers", {"name": ""})
    assert code(invalid) == (400, "validation_failed")
    assert "name" in invalid.json()["data"]["fields"]


def test_product_api_codes_are_unchanged() -> None:
    # A request without a signature: still signature_invalid (rule 11 of AGENTS.md).
    response = Client().post(
        f"/api/v1/activations/{MISSING}/check", {}, content_type="application/json"
    )
    assert code(response)[1] == "signature_invalid"
