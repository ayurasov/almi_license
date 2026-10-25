from datetime import UTC, datetime, timedelta, timezone

import pytest

from infra.clock import Clock, FrozenClock, SystemClock

MSK = timezone(timedelta(hours=3))


def test_system_clock_returns_aware_utc_and_does_not_stand_still() -> None:
    clock: Clock = SystemClock()

    first = clock.now()
    second = clock.now()

    assert first.tzinfo is UTC
    assert second >= first


def test_frozen_clock_returns_fixed_time_until_moved() -> None:
    start = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    frozen = FrozenClock(start)
    clock: Clock = frozen

    assert clock.now() == start
    assert clock.now() == start

    frozen.advance(timedelta(days=30))
    assert clock.now() == datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    frozen.advance(timedelta(hours=-1))  # clock rollback scenarios
    assert clock.now() == datetime(2026, 11, 20, 11, 0, tzinfo=UTC)

    frozen.set(start)
    assert clock.now() == start


def test_frozen_clock_normalizes_to_utc() -> None:
    clock = FrozenClock(datetime(2026, 1, 1, 3, 0, tzinfo=MSK))

    now = clock.now()

    assert now.tzinfo is UTC
    assert now == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("method", ["init", "set"])
def test_frozen_clock_rejects_naive_datetime(method: str) -> None:
    naive = datetime(2026, 1, 1, 0, 0)  # naive on purpose
    with pytest.raises(ValueError, match="timezone-aware"):
        if method == "init":
            FrozenClock(naive)
        else:
            FrozenClock(datetime(2026, 1, 1, tzinfo=UTC)).set(naive)
