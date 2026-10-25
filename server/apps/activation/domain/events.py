"""Events of the product (question 36; POST /api/v1/events, section 4 of document 2).

The module queues events (clock rollback, damaged store, failed lease check, ...) and sends them
after a successful check. They are kept per activation; a repeated delivery of an id changes
nothing. Events that point at tampering also go to the audit journal.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction

from apps.activation.models import Activation, ProductEvent
from apps.audit.domain import record
from infra.errors import DomainError

MAX_EVENTS = 100
# Signs of tampering or of a broken installation: the operator sees them in the journal.
AUDITED = frozenset({"clock_rollback_detected", "store_corrupted", "lease_verification_failed"})


@dataclass(frozen=True)
class ProductEventIn:
    id: str
    type: str
    at: datetime
    data: dict[str, Any]


def accept_events(
    activation_id: str, events: list[ProductEventIn], *, now: datetime, ip: str | None = None
) -> int:
    """Store new events of the activation; returns how many were new."""
    if len(events) > MAX_EVENTS:
        raise DomainError("payload_too_large", f"at most {MAX_EVENTS} events")
    activation = Activation.objects.filter(external_id=activation_id).first()
    if activation is None:
        raise DomainError("activation_not_found")
    new = 0
    with transaction.atomic():
        for event in events:
            _, created = ProductEvent.objects.get_or_create(
                activation=activation,
                event_id=event.id,
                defaults={
                    "type": event.type,
                    "at": event.at,
                    "data": event.data,
                    "received_at": now,
                },
            )
            if not created:
                continue
            new += 1
            if event.type in AUDITED:
                record(
                    "product",
                    f"product.{event.type}",
                    "activation",
                    activation_id,
                    at=now,
                    ip=ip,
                    data={"event_id": event.id, "at": event.at.isoformat()},
                )
    return new
