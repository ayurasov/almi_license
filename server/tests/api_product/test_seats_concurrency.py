"""E03-02: 50 parallel activations never exceed limit + reserve (real PostgreSQL)."""

from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_product.test_activate import PATH, request_body
from tests.signed import dev_device_key, signed_post

REQUESTS = 50


@pytest.fixture
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def test_fifty_parallel_activations(
    transactional_db: None, licensed: Any, issuer: Any, server_clock: FrozenClock
) -> None:
    from apps.activation.models import Activation

    licensed.limit = 10
    licensed.reserve_pct = 3  # ceil(10 * 3 / 100) = 1
    licensed.save()
    barrier = Barrier(REQUESTS)

    def one(n: int) -> tuple[int, str]:
        try:
            document = request_body(instance_id=f"00000000-0000-4000-8000-{n:012}")
            barrier.wait()
            response = signed_post(Client(), PATH, document, dev_device_key(), "device")
            code = response.json().get("code", "") if response.status_code >= 400 else ""
            return response.status_code, code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=REQUESTS) as pool:
        results = Counter(pool.map(one, range(REQUESTS)))

    assert results == {(201, ""): 11, (409, "seats_exhausted"): 39}
    assert Activation.objects.filter(license=licensed, status="active").count() == 11
    assert Activation.objects.filter(license=licensed, in_reserve=True).count() == 1
