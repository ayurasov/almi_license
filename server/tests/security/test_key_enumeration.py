"""E16-06: key enumeration (criterion 12): an unknown key and an existing key of another
product cost the same time, so timing does not tell which keys exist (within 20 %)."""

import statistics
import time
from collections.abc import Iterator
from typing import Any

import pytest

from infra.clock import FrozenClock, use_clock
from tests.api_product.test_activate import activate, code_of, request_body

pytestmark = pytest.mark.django_db
ROUNDS = 40


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def _median(document: dict[str, Any], code: str) -> float:
    durations = []
    for _ in range(ROUNDS):
        start = time.perf_counter()
        response = activate(document)
        durations.append(time.perf_counter() - start)
        assert code_of(response) == code
    return statistics.median(durations)


def test_unknown_and_existing_keys_answer_in_the_same_time(licensed: Any, issuer: Any) -> None:
    unknown = request_body(license_key="2611-ZZZZ-ZZZZ-ZZZZ")
    existing = request_body(product={"code": "alteros"})  # the key exists, the product differs
    _median(unknown, "key_not_found")  # warm up both paths
    _median(existing, "product_mismatch")
    a = _median(unknown, "key_not_found")
    b = _median(existing, "product_mismatch")
    assert abs(a - b) / max(a, b) <= 0.20, (a, b)
