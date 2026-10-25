"""Models of the outbox module (tables are owned by this module only).

Task queue in PostgreSQL and its schedule (E12-01, prompt I4-03).
"""

from django.db import models
from django.db.models import Q

from infra.db import UUIDModel


class TaskStatus(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Task(UUIDModel):
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        unique=True,
        help_text="Ключ идемпотентности постановки: задача с тем же ключом не дублируется",
    )
    status = models.CharField(max_length=8, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    run_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "run_at"], name="task_status_run_at")]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=TaskStatus.values), name="task_status")
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.status}"


class Schedule(UUIDModel):
    """A periodic task; rows are created from the schedules declared by modules."""

    name = models.CharField(max_length=64, unique=True)
    cron = models.CharField(max_length=64, help_text="Cron-выражение из пяти полей, UTC")
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField()
    last_enqueued_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name
