"""Schedule of periodic tasks (E12-01, prompt I4-03).

Modules declare schedules in code (register_schedule); schedule_due() keeps the Schedule table in
line with them and queues every due slot once. Only one process does it at a time
(pg_try_advisory_xact_lock); the task key "<schedule>:<slot>" keeps a slot from being queued twice
anyway. Missed slots (the worker was down) give one task, not one per slot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from croniter import croniter
from django.db import connection, transaction

from apps.outbox.domain.queue import enqueue
from apps.outbox.models import Schedule

# Key of pg_advisory_xact_lock for the scheduler; any constant shared by all workers.
ADVISORY_LOCK = 0x414C4D49_0001


@dataclass(frozen=True)
class Declared:
    cron: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


_declared: dict[str, Declared] = {}


def register_schedule(
    name: str, cron: str, kind: str, payload: dict[str, Any] | None = None
) -> None:
    if not croniter.is_valid(cron):
        raise ValueError(f"invalid cron expression for {name}: {cron}")
    _declared[name] = Declared(cron, kind, payload or {})


def _slot(cron: str, now: datetime, *, previous: bool) -> datetime:
    """The last slot at or before now (previous) or the first slot after now."""
    iterator = croniter(cron, now)
    if previous and croniter.match(cron, now):
        return now.replace(second=0, microsecond=0)
    value = iterator.get_prev(datetime) if previous else iterator.get_next(datetime)
    if not isinstance(value, datetime):
        raise TypeError("croniter returned no datetime")
    return value


def _sync(now: datetime) -> None:
    for name, declared in _declared.items():
        row = Schedule.objects.filter(name=name).first()
        if row is None:
            Schedule.objects.create(
                name=name,
                cron=declared.cron,
                kind=declared.kind,
                payload=declared.payload,
                next_run_at=_slot(declared.cron, now, previous=True),
            )
        elif (row.cron, row.kind, row.payload) != (declared.cron, declared.kind, declared.payload):
            row.cron, row.kind, row.payload = declared.cron, declared.kind, declared.payload
            row.next_run_at = _slot(declared.cron, now, previous=False)
            row.save(update_fields=["cron", "kind", "payload", "next_run_at"])


def schedule_due(*, now: datetime) -> int:
    """Queue the due slots of enabled schedules; returns how many tasks were queued."""
    queued = 0
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [ADVISORY_LOCK])
            (locked,) = cursor.fetchone() or (False,)
        if not locked:
            return 0
        _sync(now)
        due = Schedule.objects.select_for_update().filter(enabled=True, next_run_at__lte=now)
        for row in due:
            slot = row.next_run_at
            enqueue(row.kind, row.payload, now=now, key=f"{row.name}:{slot.isoformat()}")
            row.last_enqueued_at = now
            row.next_run_at = _slot(row.cron, now, previous=False)
            row.save(update_fields=["last_enqueued_at", "next_run_at"])
            queued += 1
    return queued
