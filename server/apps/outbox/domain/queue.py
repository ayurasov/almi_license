"""Task queue in PostgreSQL (E12-01, prompt I4-03).

A worker takes up to BATCH due tasks with SELECT ... FOR UPDATE SKIP LOCKED, so parallel workers
never take the same task. A taken task is locked for LOCK; a worker that dies leaves it to be
taken again after that. A failed task is retried after 2^attempts minutes, MAX_ATTEMPTS at most.
Handlers must be idempotent: a task can run again after a crash between its work and its status.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.outbox.models import Task, TaskStatus

BATCH = 10
MAX_ATTEMPTS = 8
LOCK = timedelta(minutes=5)
ERROR_CHARS = 2000

Handler = Callable[[dict[str, Any], datetime], None]

_handlers: dict[str, Handler] = {}
log = logging.getLogger(__name__)


def register_handler(kind: str, handler: Handler) -> None:
    """Modules register the handlers of their task kinds in AppConfig.ready()."""
    _handlers[kind] = handler


def enqueue(
    kind: str,
    payload: dict[str, Any],
    *,
    now: datetime,
    run_at: datetime | None = None,
    key: str | None = None,
) -> UUID:
    """A new task; with a key, a repeated call returns the task already queued."""
    if key is not None:
        existing = Task.objects.filter(key=key).values_list("id", flat=True).first()
        if existing is not None:
            return existing
    try:
        with transaction.atomic():
            task = Task.objects.create(
                kind=kind, payload=payload, key=key, run_at=run_at or now, created_at=now
            )
    except IntegrityError:
        # Another process queued the same key between the check and the insert.
        return Task.objects.values_list("id", flat=True).get(key=key)
    return task.id


def claim(*, now: datetime) -> list[Task]:
    """Take up to BATCH due tasks (pending ones and running ones whose lock expired)."""
    due = Q(status=TaskStatus.PENDING, run_at__lte=now) | Q(
        status=TaskStatus.RUNNING, locked_until__lt=now
    )
    with transaction.atomic():
        tasks = list(
            Task.objects.select_for_update(skip_locked=True)
            .filter(due)
            .order_by("run_at", "created_at")[:BATCH]
        )
        for task in tasks:
            task.status = TaskStatus.RUNNING
            task.locked_until = now + LOCK
            task.save(update_fields=["status", "locked_until"])
    return tasks


def execute(task: Task, *, now: datetime) -> None:
    handler = _handlers.get(task.kind)
    if handler is None:
        _finish(task, TaskStatus.FAILED, now, f"no handler for {task.kind}")
        return
    try:
        handler(task.payload, now)
    except Exception as error:  # any failure of a task is retried
        task.attempts += 1
        message = f"{type(error).__name__}: {error}"[:ERROR_CHARS]
        log.warning("task %s %s failed, attempt %d", task.kind, task.id, task.attempts)
        if task.attempts >= MAX_ATTEMPTS:
            _finish(task, TaskStatus.FAILED, now, message)
        else:
            task.status = TaskStatus.PENDING
            task.run_at = now + timedelta(minutes=2**task.attempts)
            task.locked_until = None
            task.last_error = message
            task.save(update_fields=["status", "run_at", "locked_until", "last_error", "attempts"])
        return
    _finish(task, TaskStatus.DONE, now, "")


def _finish(task: Task, status: str, now: datetime, error: str) -> None:
    task.status = status
    task.locked_until = None
    task.finished_at = now
    if error:
        task.last_error = error
    task.save(update_fields=["status", "locked_until", "finished_at", "last_error", "attempts"])


def run_due(*, now: datetime) -> int:
    """Run one batch of due tasks; returns how many were run."""
    tasks = claim(now=now)
    for task in tasks:
        execute(task, now=now)
    return len(tasks)


def queue_size(*, now: datetime) -> int:
    """Due tasks not yet taken (metric of E15-05)."""
    return Task.objects.filter(status=TaskStatus.PENDING, run_at__lte=now).count()


def failed_count() -> int:
    """Tasks that ran out of attempts (metric of E15-05)."""
    return Task.objects.filter(status=TaskStatus.FAILED).count()
