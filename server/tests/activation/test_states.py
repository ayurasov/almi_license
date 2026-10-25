"""E12-03: hourly recalculation of licence states through PolicyEngine."""

from datetime import timedelta
from typing import Any

from apps.activation.domain import recompute_states
from apps.audit.models import AuditEvent
from apps.outbox.domain import enqueue, run_due
from infra.clock import FrozenClock


def state_of(license_: Any) -> str:
    license_.refresh_from_db()
    return str(license_.state)


def test_states_follow_the_term(licensed: Any, clock: FrozenClock) -> None:
    licensed.enforcement = "enforce"
    licensed.save()
    assert recompute_states(now=clock.now()) == 1
    assert state_of(licensed) == "ACTIVE"
    licensed.refresh_from_db()
    assert licensed.state_at == clock.now()
    assert licensed.valid_until is not None
    until = licensed.valid_until
    recompute_states(now=until - timedelta(days=10))
    assert state_of(licensed) == "NOTICE"
    recompute_states(now=until + timedelta(days=3))
    assert state_of(licensed) == "GRACE"
    recompute_states(now=until + timedelta(days=20))
    assert state_of(licensed) == "RESTRICTED"


def test_revoked_and_no_audit(licensed: Any, clock: FrozenClock) -> None:
    rights = licensed.rights_version
    licensed.status = "revoked"
    licensed.save()
    recompute_states(now=clock.now())
    assert state_of(licensed) == "REVOKED"
    assert licensed.rights_version == rights
    assert not AuditEvent.objects.exists()


def test_task_through_the_queue(licensed: Any, clock: FrozenClock) -> None:
    enqueue("licensing.recompute_states", {}, now=clock.now())
    run_due(now=clock.now())
    assert state_of(licensed) != ""


def test_statistics_show_the_states(licensed: Any, clock: FrozenClock) -> None:
    from apps.stats.domain import license_stats

    recompute_states(now=clock.now())
    summary = license_stats()
    assert summary.by_state == {"ACTIVE": 1}
    assert summary.rows[0].state == "ACTIVE"
