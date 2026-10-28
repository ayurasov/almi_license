"""The only source of current time on the server (AGENTS.md, rule 4).

Code receives a Clock and calls clock.now(); datetime.now() and time.time()
are forbidden everywhere else. Tests use FrozenClock.
"""

import os
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


class StandClock:
    """System time moved by the seconds written in a file: time shifts of test stands (E16-04).

    The file is read again when it changes, so a test moves the time of a running API and worker.
    Never in production (settings/prod.py refuses CLOCK_OFFSET_FILE).
    """

    def __init__(self, offset_file: str) -> None:
        self._path = offset_file
        self._seen: tuple[float, timedelta] = (-1.0, timedelta())

    def offset(self) -> timedelta:
        try:
            stamp = os.stat(self._path).st_mtime
        except OSError:
            return timedelta()
        if stamp != self._seen[0]:
            try:
                with open(self._path, encoding="ascii") as file:
                    seconds = float(file.read().strip() or 0)
            except (OSError, ValueError):
                seconds = 0.0
            self._seen = (stamp, timedelta(seconds=seconds))
        return self._seen[1]

    def now(self) -> datetime:
        return datetime.now(UTC) + self.offset()


def install_clock(clock: Clock) -> None:
    """The clock of the whole process from its start (settings of a test stand)."""
    global _current
    _current = clock


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
