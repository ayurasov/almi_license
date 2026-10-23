import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from infra.clock import FrozenClock


def event(clock: FrozenClock, seq: int, hash_: str, prev: str = "") -> AuditEvent:
    return AuditEvent.objects.create(seq=seq, actor="operator:test", action="license.created",
                                     object_type="license", object_id="6f1c2a4e", at=clock.now(),
                                     ip="10.0.0.1", data={}, prev_hash=prev, hash=hash_)


@pytest.mark.django_db
def test_chain_position_and_hash_are_unique(clock: FrozenClock) -> None:
    event(clock, 1, "a" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        event(clock, 1, "b" * 64, prev="a" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        event(clock, 2, "a" * 64, prev="a" * 64)
    event(clock, 2, "b" * 64, prev="a" * 64)
