"""E05-03: limits of the Product API (section 4.7 of document 2): 429 rate_limited, Retry-After."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client, override_settings

from infra.clock import FrozenClock, use_clock
from tests.api_product.test_activate import activate, code_of, request_body
from tests.api_product.test_check import check, check_body
from tests.contract import openapi_errors

pytestmark = pytest.mark.django_db
LIMITS = {
    "activate_ip": 3,
    "activate_key": 5,
    "check_ip": 100,
    "check_activation": 2,
    "offline_ip": 2,
}


@pytest.fixture(autouse=True)
def limits(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock), override_settings(PRODUCT_RATE_LIMITS=LIMITS):
        yield clock


def test_activation_per_ip_a_minute(licensed: Any, issuer: Any, limits: FrozenClock) -> None:
    codes = [activate(request_body()).status_code for _ in range(4)]
    assert codes[:3] == [201, 200, 200]  # the same instance: a repeat is still counted
    refused = activate(request_body())
    assert refused.status_code == 429 and code_of(refused) == "rate_limited"
    assert 0 < int(refused["Retry-After"]) <= 60
    assert openapi_errors("Problem", refused.json()) == []
    limits.advance(timedelta(minutes=1))
    assert activate(request_body()).status_code == 200


def test_activation_per_key_an_hour(licensed: Any, issuer: Any, limits: FrozenClock) -> None:
    for minute in range(5):
        limits.set(limits.now() + timedelta(minutes=minute and 1))
        assert activate(request_body()).status_code in (200, 201)
    limits.advance(timedelta(minutes=1))
    refused = activate(request_body())
    assert refused.status_code == 429
    assert int(refused["Retry-After"]) > 60  # the hour window


def test_check_per_activation_an_hour(licensed: Any, issuer: Any) -> None:
    activation_id = activate(request_body()).json()["activation_id"]
    assert check(activation_id, check_body(1)).status_code == 200
    assert check(activation_id, check_body(2)).status_code == 200
    refused = check(activation_id, check_body(3))
    assert refused.status_code == 429 and code_of(refused) == "rate_limited"


def test_offline_files_per_ip_an_hour(licensed: Any) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    def upload() -> Any:
        file = SimpleUploadedFile("x.alk-req", b"{}", content_type="application/octet-stream")
        return Client().post("/api/v1/offline/requests", {"file": file})

    assert [upload().status_code for _ in range(2)] == [400, 400]  # counted before parsing
    assert upload().status_code == 429


def test_limited_answer_is_not_replayed(licensed: Any, issuer: Any, limits: FrozenClock) -> None:
    from tests.api_product.test_activate import REPEAT_ID
    from tests.signed import dev_device_key, signed_post

    for _ in range(3):
        activate(request_body())

    def again() -> Any:
        client = Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID)
        return signed_post(
            client, "/api/v1/activations", request_body(), dev_device_key(), "device"
        )

    assert again().status_code == 429
    limits.advance(timedelta(minutes=1))
    assert again().status_code == 200  # the 429 was not kept for the Idempotency-Key


def test_zero_turns_a_limit_off(licensed: Any, issuer: Any) -> None:
    with override_settings(PRODUCT_RATE_LIMITS=LIMITS | {"activate_ip": 0, "activate_key": 0}):
        assert {activate(request_body()).status_code for _ in range(8)} <= {200, 201}
