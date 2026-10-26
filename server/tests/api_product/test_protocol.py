"""ALMI-Protocol (section 4 of document 2): version 1 is served, another one gets 426
upgrade_required; a request without the header is accepted, counted and logged (as question 37)."""

from typing import Any

import pytest
from django.test import Client

from infra import metrics
from tests.api_product.test_activate import PATH, code_of, request_body
from tests.signed import dev_device_key, signed_post

pytestmark = pytest.mark.django_db


def activate(headers: dict[str, str] | None) -> Any:
    return signed_post(Client(), PATH, request_body(), dev_device_key(), "device", headers)


def missing() -> float:
    value = metrics.REGISTRY.get_sample_value(
        "almi_product_requests_without_protocol_total", {"operation": "Activate"}
    )
    return value or 0.0


def test_version_1_is_served(licensed: Any, issuer: Any) -> None:
    assert activate({"ALMI-Protocol": "1"}).status_code == 201


@pytest.mark.parametrize("value", ["2", "0", "v1", ""])
def test_another_version_is_refused_with_426(licensed: Any, issuer: Any, value: str) -> None:
    response = activate({"ALMI-Protocol": value} if value else {"ALMI-Protocol": " "})
    assert response.status_code == 426
    assert code_of(response) == "upgrade_required"


def test_missing_header_is_accepted_and_counted(
    licensed: Any, issuer: Any, caplog: pytest.LogCaptureFixture
) -> None:
    before = missing()
    with caplog.at_level("INFO"):
        assert activate(None).status_code == 201
    assert missing() == before + 1
    assert any("without ALMI-Protocol" in r.getMessage() for r in caplog.records)


def test_trust_checks_the_version_too() -> None:
    assert Client().get("/api/v1/trust", headers={"ALMI-Protocol": "2"}).status_code == 426


def test_offline_portal_is_not_a_product(licensed: Any, issuer: Any) -> None:
    # The portal is a browser page: it never sends the header and is not refused for it.
    reply = Client().post("/api/v1/offline/requests", {}, headers={"ALMI-Protocol": "2"})
    assert reply.status_code != 426
