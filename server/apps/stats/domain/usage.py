"""Usage counters reported by products (E03-04, E11-02)."""

from typing import Any

from apps.stats.models import UsageRecord


def latest_usage(activation_ids: list[str]) -> dict[str, dict[str, Any]]:
    """The last usage counters of each activation."""
    rows = (
        UsageRecord.objects.filter(activation_id__in=activation_ids)
        .order_by("activation_id", "-at")
        .distinct("activation_id")
    )
    return {row.activation_id: row.usage for row in rows}
