"""Domain services of the stats module."""

from datetime import datetime
from typing import Any

from apps.stats.models import UsageRecord


def record_usage(activation_id: str, at: datetime, usage: dict[str, Any]) -> None:
    """Keep the counters of a check as a separate record for statistics (E03-04)."""
    UsageRecord.objects.create(activation_id=activation_id, at=at, usage=usage)


__all__ = ["record_usage"]
