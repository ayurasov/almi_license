"""Domain services of the stats module."""

from datetime import datetime
from typing import Any

from apps.stats.domain.denials import DENIAL_CODES, denials_between, record_denial
from apps.stats.domain.summary import LicenseStats, Summary, license_stats, stats_workbook
from apps.stats.domain.usage import latest_usage
from apps.stats.models import UsageRecord


def record_usage(activation_id: str, at: datetime, usage: dict[str, Any]) -> None:
    """Keep the counters of a check as a separate record for statistics (E03-04)."""
    UsageRecord.objects.create(activation_id=activation_id, at=at, usage=usage)


__all__ = [
    "DENIAL_CODES",
    "denials_between",
    "record_denial",
    "LicenseStats",
    "Summary",
    "latest_usage",
    "license_stats",
    "record_usage",
    "stats_workbook",
]
