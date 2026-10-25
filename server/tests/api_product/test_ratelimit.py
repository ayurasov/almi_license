"""Rate limits shared by processes (section 4.7 of document 2)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django.db import connection

from apps.api_product.domain.ratelimit import (
    Limit,
    Limited,
    block,
    blocked,
    hit,
    purge_counters,
)
from apps.api_product.models import RateCounter

NOW = datetime(2026, 11, 2, 8, 15, 20, tzinfo=UTC)
PER_MINUTE = Limit("test.key", 3, timedelta(minutes=1))


def test_limit_and_retry_after(db: None) -> None:
    for _ in range(3):
        hit(PER_MINUTE, "2645-7KQ9-MX2D-81ZT", now=NOW)
    with pytest.raises(Limited) as refused:
        hit(PER_MINUTE, "2645-7KQ9-MX2D-81ZT", now=NOW)
    assert refused.value.retry_after == 40  # the window ends at 08:16:00
    hit(PER_MINUTE, "another", now=NOW)  # keys are counted apart
    hit(PER_MINUTE, "2645-7KQ9-MX2D-81ZT", now=NOW + timedelta(seconds=40))  # next window


def test_table_holds_no_value_in_clear(db: None) -> None:
    hit(PER_MINUTE, "2645-7KQ9-MX2D-81ZT", now=NOW)
    (key,) = RateCounter.objects.values_list("key", flat=True)
    assert "2645" not in key and key.startswith("test.key:")


def test_parallel_requests_never_pass_the_limit(transactional_db: None) -> None:
    barrier = Barrier(10)

    def one(_: int) -> bool:
        try:
            barrier.wait()
            hit(PER_MINUTE, "shared", now=NOW)
            return True
        except Limited:
            return False
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(one, range(10))) == 3


def test_block_until(db: None) -> None:
    block("test.ip", "198.51.100.7", until=NOW + timedelta(seconds=900))
    with pytest.raises(Limited) as refused:
        blocked("test.ip", "198.51.100.7", now=NOW)
    assert refused.value.retry_after == 900
    blocked("test.ip", "198.51.100.7", now=NOW + timedelta(seconds=900))


def test_purge(db: None) -> None:
    hit(PER_MINUTE, "old", now=NOW - timedelta(days=2))
    hit(PER_MINUTE, "new", now=NOW)
    block("test.ip", "198.51.100.7", until=NOW - timedelta(seconds=1))
    assert purge_counters(NOW) == 2
    assert RateCounter.objects.count() == 1
