"""Rate limits in PostgreSQL (section 4.7 of document 2).

hit() counts a request of a key in a fixed window with one atomic upsert, so the limit holds
across processes and servers sharing the database. Keys are hashes (key_of): a licence key or an
IP never reaches the table or the logs in clear (AGENTS.md, rule 9).
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import connection

from apps.api_product.models import RateBlock, RateCounter


@dataclass(frozen=True)
class Limit:
    name: str
    count: int
    window: timedelta


class Limited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"retry after {retry_after} s")
        self.retry_after = retry_after


def key_of(name: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return f"{name}:{digest}"


def _window_start(now: datetime, window: timedelta) -> datetime:
    size = int(window.total_seconds())
    start = int(now.timestamp()) // size * size
    return datetime.fromtimestamp(start, UTC)


def count(name: str, value: str, window: timedelta, *, now: datetime) -> int:
    """Count one request of the key in its window; the number in the window including it."""
    return _count(key_of(name, value), _window_start(now, window))


def hit(limit: Limit, value: str, *, now: datetime) -> None:
    """Count one request; Limited when the window already had limit.count requests."""
    start = _window_start(now, limit.window)
    total = _count(key_of(limit.name, value), start)
    if total > limit.count:
        raise Limited(math.ceil((start + limit.window - now).total_seconds()))


def _count(key: str, start: datetime) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {RateCounter._meta.db_table} (id, key, window_start, count)
            VALUES (gen_random_uuid(), %s, %s, 1)
            ON CONFLICT (key, window_start) DO UPDATE
                SET count = {RateCounter._meta.db_table}.count + 1
            RETURNING count
            """,  # noqa: S608 - the table name is a model constant, values are parameters
            [key, start],
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 1


def block(name: str, value: str, *, until: datetime) -> None:
    RateBlock.objects.update_or_create(key=key_of(name, value), defaults={"until": until})


def blocked(name: str, value: str, *, now: datetime) -> None:
    """Limited while the key is blocked."""
    until = (
        RateBlock.objects.filter(key=key_of(name, value), until__gt=now)
        .values_list("until", flat=True)
        .first()
    )
    if until is not None:
        raise Limited(math.ceil((until - now).total_seconds()))


def purge_counters(now: datetime, *, older_than: timedelta = timedelta(days=1)) -> int:
    deleted, _ = RateCounter.objects.filter(window_start__lt=now - older_than).delete()
    gone, _ = RateBlock.objects.filter(until__lt=now).delete()
    return deleted + gone
