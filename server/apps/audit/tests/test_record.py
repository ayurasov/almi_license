"""audit.domain.record(): hash chain (section 7.1 of document 1, AGENTS.md rule 7)."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from apps.audit.domain import record, verify_chain

AT = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)
pytestmark = pytest.mark.django_db


def test_events_form_a_hash_chain() -> None:
    from apps.audit.models import AuditEvent

    first = record("product", "activation.created", "activation", "act_1", at=AT, data={"a": 1})
    second = record("operator:1", "license.updated", "license", "l1", at=AT, ip="10.0.0.1")

    assert (first.seq, second.seq) == (1, 2)
    assert first.prev_hash == "" and second.prev_hash == first.hash
    content: dict[str, Any] = {
        "seq": 1,
        "actor": "product",
        "action": "activation.created",
        "object_type": "activation",
        "object_id": "act_1",
        "at": "2026-11-02T08:15:00Z",
        "ip": None,
        "data": {"a": 1},
        "prev_hash": "",
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert first.hash == hashlib.sha256(canonical.encode()).hexdigest()
    assert verify_chain() == 2
    assert AuditEvent.objects.count() == 2


def test_tampering_breaks_the_chain() -> None:
    from apps.audit.models import AuditEvent

    record("product", "activation.created", "activation", "act_1", at=AT)
    record("product", "activation.created", "activation", "act_2", at=AT)
    AuditEvent.objects.filter(seq=1).update(object_id="act_X")

    with pytest.raises(ValueError, match="seq 1"):
        verify_chain()


def test_naive_time_is_refused() -> None:
    with pytest.raises(ValueError):
        record("product", "x", "y", "z", at=datetime(2026, 1, 1))  # noqa: DTZ001
