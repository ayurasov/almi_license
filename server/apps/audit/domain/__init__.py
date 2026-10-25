"""audit.domain.record(): every change of rights writes an event (AGENTS.md, rule 7).

Events form a hash chain: hash = SHA-256 of the canonical JSON of the event with prev_hash.
Writers are serialised by a transaction-level advisory lock, so seq has no gaps or forks;
the event is part of the caller's transaction.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from django.db import connection, transaction
from django.db.models import Q, QuerySet

from apps.audit.models import AuditEvent

# pg_advisory_xact_lock key of the audit chain ("audit" in ASCII)
_CHAIN_LOCK = 0x6175646974


def _hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content(event: AuditEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "actor": event.actor,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "at": event.at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "ip": event.ip,
        "data": event.data,
        "prev_hash": event.prev_hash,
    }


def record(
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    *,
    at: datetime,
    ip: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an event; data must not contain secrets (AGENTS.md, rules 8 and 9)."""
    if at.utcoffset() is None:
        raise ValueError("audit time must carry a timezone")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_CHAIN_LOCK])
        last = AuditEvent.objects.order_by("-seq").only("seq", "hash").first()
        event = AuditEvent(
            seq=1 if last is None else last.seq + 1,
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            at=at,
            ip=ip,
            data=data or {},
            prev_hash="" if last is None else last.hash,
        )
        event.hash = _hash(_content(event))
        event.save()
    return event


def verify_chain() -> int:
    """Recompute the chain; ValueError names the first broken seq. Returns the event count."""
    previous = ""
    count = 0
    for event in AuditEvent.objects.order_by("seq").iterator():
        count += 1
        if (
            event.seq != count
            or event.prev_hash != previous
            or event.hash != _hash(_content(event))
        ):
            raise ValueError(f"audit chain is broken at seq {event.seq}")
        previous = event.hash
    return count


def events_for(object_type: str, object_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """History of one object for the console card (newest first)."""
    rows = AuditEvent.objects.filter(object_type=object_type, object_id=object_id).order_by("-seq")[
        :limit
    ]
    return [
        {"seq": e.seq, "at": e.at, "actor": e.actor, "action": e.action, "data": e.data}
        for e in rows
    ]


@dataclass(frozen=True)
class EventFilter:
    """Filters of the audit screen (E10-04); objects limits the events to a set of objects."""

    object_type: str = ""
    object_id: str = ""
    actor: str = ""
    action: str = ""
    since: datetime | None = None
    until: datetime | None = None
    objects: frozenset[tuple[str, str]] | None = None


@dataclass(frozen=True)
class EventData:
    seq: int
    at: datetime
    actor: str
    action: str
    object_type: str
    object_id: str
    ip: str | None
    data: dict[str, Any]


MAX_PAGE_SIZE = 200
MAX_EXPORT = 100_000
CSV_COLUMNS = ("seq", "at", "actor", "action", "object_type", "object_id", "ip", "data")


def _events(query: EventFilter) -> QuerySet[AuditEvent]:
    rows = AuditEvent.objects.all()
    if query.object_type:
        rows = rows.filter(object_type=query.object_type)
    if query.object_id:
        rows = rows.filter(object_id=query.object_id)
    if query.actor:
        rows = rows.filter(actor__icontains=query.actor)
    if query.action:
        # A type is an action or its prefix: "license." finds every licence event.
        rows = rows.filter(action__startswith=query.action)
    if query.since is not None:
        rows = rows.filter(at__gte=query.since)
    if query.until is not None:
        rows = rows.filter(at__lt=query.until)
    if query.objects is not None:
        by_type: dict[str, list[str]] = {}
        for object_type, object_id in query.objects:
            by_type.setdefault(object_type, []).append(object_id)
        scope = Q(pk__in=[])
        for object_type, ids in by_type.items():
            scope |= Q(object_type=object_type, object_id__in=ids)
        rows = rows.filter(scope)
    return rows.order_by("-seq")


def _data(event: AuditEvent) -> EventData:
    return EventData(
        event.seq,
        event.at,
        event.actor,
        event.action,
        event.object_type,
        event.object_id,
        event.ip,
        event.data,
    )


def search_events(
    query: EventFilter, *, page: int = 1, page_size: int = 50
) -> tuple[int, list[EventData]]:
    """A page of events, newest first (E10-04)."""
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("bad page")
    rows = _events(query)
    start = (page - 1) * page_size
    return rows.count(), [_data(e) for e in rows[start : start + page_size]]


def _cell(value: str) -> str:
    # A cell that a spreadsheet would read as a formula is quoted (CSV injection).
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def events_csv(query: EventFilter) -> str:
    """The filtered journal as CSV (UTF-8, comma), at most MAX_EXPORT rows."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for event in _events(query)[:MAX_EXPORT]:
        writer.writerow(
            [
                event.seq,
                event.at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                _cell(event.actor),
                _cell(event.action),
                _cell(event.object_type),
                _cell(event.object_id),
                event.ip or "",
                _cell(json.dumps(event.data, ensure_ascii=False, sort_keys=True)),
            ]
        )
    return out.getvalue()


def last_digest() -> str:
    """Hash of the last event of the chain ("" for an empty journal), for usage reports."""
    value = AuditEvent.objects.order_by("-seq").values_list("hash", flat=True).first()
    return value or ""


__all__ = [
    "last_digest",
    "EventData",
    "EventFilter",
    "events_csv",
    "events_for",
    "record",
    "search_events",
    "verify_chain",
]
