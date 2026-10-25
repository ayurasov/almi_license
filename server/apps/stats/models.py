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


class DenialCount(UUIDModel):
    """Refused product requests by error code and hour (question 43; .alk-usage denials)."""

    hour = models.DateTimeField()
    code = models.CharField(max_length=64)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hour", "code"], name="stats_denial_hour_code")
        ]

    def __str__(self) -> str:
        return f"{self.code}@{self.hour.isoformat()}: {self.count}"
