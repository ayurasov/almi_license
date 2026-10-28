"""Refused product requests by code (question 43): the denials of the .alk-usage report.

Counted per hour: one row per code and hour, written by an upsert, so concurrent refusals do not
lose counts. A report sums the whole hours [hour of since, hour of until): the current hour goes
to the next report, whose since is this until, so no hour is counted twice.
"""

from datetime import datetime

from django.db import connection
from django.db.models import Sum

from apps.stats.models import DenialCount

# Codes of section 16 of document 2 that refuse the product a licence or a seat.
DENIAL_CODES = frozenset(
    {
        "invalid_key_format",
        "key_not_found",
        "product_mismatch",
        "license_expired",
        "license_revoked",
        "seats_exhausted",
        "instance_conflict",
        "rebind_required",
        "unsupported_product_version",
        "activation_released",
        "activation_not_found",
        "signature_invalid",
        "rate_limited",
    }
)


def _hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def record_denial(code: str, *, now: datetime) -> None:
    if code not in DENIAL_CODES:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {DenialCount._meta.db_table} (id, hour, code, count)
            VALUES (gen_random_uuid(), %s, %s, 1)
            ON CONFLICT (hour, code) DO UPDATE SET count = {DenialCount._meta.db_table}.count + 1
            """,  # noqa: S608 - the table name is a model constant, values are parameters
            [_hour(now), code],
        )


def denials_between(since: datetime, until: datetime) -> dict[str, int]:
    """Refusals by code in the whole hours of the period."""
    rows = (
        DenialCount.objects.filter(hour__gte=_hour(since), hour__lt=_hour(until))
        .values("code")
        .annotate(total=Sum("count"))
        .order_by("code")
    )
    return {row["code"]: int(row["total"]) for row in rows}
