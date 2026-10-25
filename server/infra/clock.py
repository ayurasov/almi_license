"""The only source of current time on the server (AGENTS.md, rule 4).

Code receives a Clock and calls clock.now(); datetime.now() and time.time()
are forbidden everywhere else. Tests use FrozenClock.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as a timezone-aware datetime in UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Clock for tests: stands still until moved with advance() or set()."""

    def __init__(self, at: datetime) -> None:
        self._now = _as_utc(at)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        """Move the clock by delta; a negative delta models a clock rollback."""
        self._now += delta

    def set(self, at: datetime) -> None:
        self._now = _as_utc(at)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FrozenClock needs a timezone-aware datetime")
    return value.astimezone(UTC)


_current: Clock = SystemClock()


def current_clock() -> Clock:
    """Clock of the running process; entry points (views, commands) pass it to domain code."""
    return _current


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Replace the process clock for the duration of the block (tests)."""
    global _current
    previous, _current = _current, clock
    try:
        yield clock
    finally:
        _current = previous


def monotonic() -> float:
    """Seconds of a monotonic clock, for durations only (metrics); never a moment in time."""
    return time.perf_counter()
