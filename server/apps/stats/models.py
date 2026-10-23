"""Models of the stats module (tables are owned by this module only)."""

from django.db import models

from infra.db import UUIDModel


class UsageRecord(UUIDModel):
    """Usage counters of one check (section 5.3 of document 2; statistics, section 11 of doc. 1)."""

    activation_id = models.CharField(max_length=30, help_text="act_ + ULID")
    at = models.DateTimeField()
    usage = models.JSONField()

    class Meta:
        indexes = [models.Index(fields=["activation_id", "at"], name="stats_usage_activation_at")]

    def __str__(self) -> str:
        return f"{self.activation_id}@{self.at.isoformat()}"
