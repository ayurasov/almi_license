"""audit.domain.record(): every change of rights writes an event (AGENTS.md, rule 7).

Events form a hash chain: hash = SHA-256 of the canonical JSON of the event with prev_hash.
Writers are serialised by a transaction-level advisory lock, so seq has no gaps or forks;
the event is part of the caller's transaction.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from django.db import connection, transaction

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


__all__ = ["events_for", "record", "verify_chain"]
