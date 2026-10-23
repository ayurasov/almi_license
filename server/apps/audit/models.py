"""Audit log with a hash chain (docs/specs/01-architecture.md, section 7.1).

Written only by audit.domain.record().
"""

from django.db import models

from infra.db import UUIDModel


class AuditEvent(UUIDModel):
    seq = models.PositiveBigIntegerField(unique=True, help_text="Позиция в цепочке хэшей")
    actor = models.CharField(max_length=256)
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True, default="")
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_event_object"),
            models.Index(fields=["at"], name="audit_event_at"),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} {self.action}"
