"""E12-01: task queue in PostgreSQL (prompt I4-03)."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any

import pytest
from django.db import connection

from apps.outbox.domain import (
    MAX_ATTEMPTS,
    claim,
    enqueue,
    register_handler,
    register_schedule,
    run_due,
    schedule,
    schedule_due,
)
from apps.outbox.models import Schedule, Task, TaskStatus
from infra.clock import FrozenClock

NOW = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)
calls: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def handlers() -> Iterator[None]:
    calls.clear()

    def ok(payload: dict[str, Any], now: datetime) -> None:
        calls.append(payload)

    def boom(payload: dict[str, Any], now: datetime) -> None:
        raise RuntimeError("broken")

    register_handler("test.ok", ok)
    register_handler("test.boom", boom)
    declared = dict(schedule._declared)
    schedule._declared.clear()  # only the schedules of the test
    yield
    schedule._declared.clear()
    schedule._declared.update(declared)


def test_task_runs_once(db: None) -> None:
    enqueue("test.ok", {"n": 1}, now=NOW)
    assert run_due(now=NOW) == 1
    assert run_due(now=NOW) == 0
    task = Task.objects.get()
    assert task.status == TaskStatus.DONE
    assert calls == [{"n": 1}]


def test_task_waits_for_run_at(db: None) -> None:
    enqueue("test.ok", {}, now=NOW, run_at=NOW + timedelta(minutes=5))
    assert run_due(now=NOW) == 0
    assert run_due(now=NOW + timedelta(minutes=5)) == 1


def test_failed_task_is_retried_with_backoff(db: None) -> None:
    enqueue("test.boom", {}, now=NOW)
    run_due(now=NOW)
    task = Task.objects.get()
    assert task.status == TaskStatus.PENDING
    assert task.attempts == 1
    assert task.run_at == NOW + timedelta(minutes=2)
    assert "broken" in task.last_error
    # Not due before the delay.
    assert run_due(now=NOW + timedelta(minutes=1)) == 0
    run_due(now=NOW + timedelta(minutes=2))
    task.refresh_from_db()
    assert task.attempts == 2
    assert task.run_at == NOW + timedelta(minutes=2 + 4)


def test_task_fails_after_max_attempts(db: None) -> None:
    enqueue("test.boom", {}, now=NOW)
    at = NOW
    for _ in range(MAX_ATTEMPTS):
        run_due(now=at)
        at += timedelta(days=1)
    task = Task.objects.get()
    assert task.attempts == MAX_ATTEMPTS
    assert task.status == TaskStatus.FAILED
    assert run_due(now=at) == 0


def test_unknown_kind_fails_without_retry(db: None) -> None:
    enqueue("test.missing", {}, now=NOW)
    run_due(now=NOW)
    task = Task.objects.get()
    assert task.status == TaskStatus.FAILED
    assert "test.missing" in task.last_error


def test_stuck_running_task_is_taken_again(db: None) -> None:
    enqueue("test.ok", {}, now=NOW)
    assert [t.kind for t in claim(now=NOW)] == ["test.ok"]
    # The worker died: the lock expires, another worker takes the task.
    assert claim(now=NOW + timedelta(minutes=1)) == []
    assert len(claim(now=NOW + timedelta(minutes=10))) == 1


def test_enqueue_with_key_is_idempotent(db: None) -> None:
    first = enqueue("test.ok", {}, now=NOW, key="hourly:2026-11-02T08")
    second = enqueue("test.ok", {}, now=NOW, key="hourly:2026-11-02T08")
    assert first == second
    assert Task.objects.count() == 1


def test_two_workers_never_take_the_same_task(transactional_db: None) -> None:
    for n in range(30):
        enqueue("test.ok", {"n": n}, now=NOW)
    barrier = Barrier(3)

    def worker(_: int) -> list[str]:
        try:
            barrier.wait()
            taken: list[str] = []
            while batch := claim(now=NOW):
                taken += [str(t.id) for t in batch]
            return taken
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(worker, range(3)))
    every = [task for taken in results for task in taken]
    assert len(every) == 30
    assert len(set(every)) == 30


def test_schedule_enqueues_each_slot_once(db: None) -> None:
    register_schedule("test.hourly", "0 * * * *", "test.ok")
    clock = FrozenClock(NOW)
    assert schedule_due(now=clock.now()) == 1  # first tick: the current hour is due
    assert schedule_due(now=clock.now()) == 0
    clock.advance(timedelta(minutes=30))
    assert schedule_due(now=clock.now()) == 0
    clock.advance(timedelta(minutes=15))  # 09:00 passed
    assert schedule_due(now=clock.now()) == 1
    assert Task.objects.filter(kind="test.ok").count() == 2


def test_disabled_schedule_is_skipped(db: None) -> None:
    register_schedule("test.hourly", "0 * * * *", "test.ok")
    schedule_due(now=NOW)
    Schedule.objects.filter(name="test.hourly").update(enabled=False)
    assert schedule_due(now=NOW + timedelta(hours=3)) == 0


def test_schedule_runs_in_one_worker_only(transactional_db: None) -> None:
    register_schedule("test.hourly", "0 * * * *", "test.ok")
    barrier = Barrier(4)

    def tick(_: int) -> int:
        try:
            barrier.wait()
            return schedule_due(now=NOW)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(tick, range(4))) == 1
    assert Task.objects.count() == 1
