"""E12-02: automatic release of activations without contact (prompt I4-03)."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from apps.activation.domain import release_stale_activations
from apps.activation.models import Activation
from apps.audit.models import AuditEvent
from apps.outbox.domain import enqueue, run_due
from infra.clock import FrozenClock

DAYS = 30  # release_after_days of POLICY in conftest.py


@pytest.fixture
def make(licensed: Any, make_activation: Callable[..., Activation]) -> Callable[..., Activation]:
    counter = iter(range(1000))

    def one(**fields: Any) -> Activation:
        n = next(counter)
        return make_activation(
            external_id=f"act_01JABF8Q4W2N8C1R7ZB0Y5K{n:03X}",
            instance_id=f"00000000-0000-4000-8000-{n:012}",
            **fields,
        )

    return one


def test_stale_activation_is_released(make: Any, clock: FrozenClock) -> None:
    stale = make(last_seen_at=clock.now() - timedelta(days=DAYS, seconds=1))
    fresh = make(last_seen_at=clock.now() - timedelta(days=DAYS - 1))
    assert release_stale_activations(now=clock.now()) == 1
    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == "released_auto"
    assert stale.released_at == clock.now()
    assert fresh.status == "active"
    event = AuditEvent.objects.get(action="activation.released_auto")
    assert event.object_id == stale.external_id
    assert event.actor == "system"


def test_boundary_exactly_release_after_days_is_kept(make: Any, clock: FrozenClock) -> None:
    edge = make(last_seen_at=clock.now() - timedelta(days=DAYS))
    assert release_stale_activations(now=clock.now()) == 0
    clock.advance(timedelta(microseconds=1))
    assert release_stale_activations(now=clock.now()) == 1
    edge.refresh_from_db()
    assert edge.status == "released_auto"


def test_profile_value_is_used(make: Any, licensed: Any, clock: FrozenClock) -> None:
    from apps.catalog.models import PolicyProfile

    profile = PolicyProfile.objects.get(code="alteroffice-desktop.commercial")
    profile.params = profile.params | {"release_after_days": 7}
    profile.save()
    row = make(last_seen_at=clock.now() - timedelta(days=8))
    assert release_stale_activations(now=clock.now()) == 1
    row.refresh_from_db()
    assert row.status == "released_auto"


def test_only_active_activations_are_released(make: Any, clock: FrozenClock) -> None:
    old = clock.now() - timedelta(days=90)
    make(last_seen_at=old, status="released", released_at=old)
    make(last_seen_at=old, status="revoked")
    make(last_seen_at=old, status="conflict")
    assert release_stale_activations(now=clock.now()) == 0
    assert not AuditEvent.objects.filter(action="activation.released_auto").exists()


def test_repeated_run_changes_nothing(make: Any, clock: FrozenClock) -> None:
    make(last_seen_at=clock.now() - timedelta(days=DAYS + 1))
    assert release_stale_activations(now=clock.now()) == 1
    assert release_stale_activations(now=clock.now()) == 0
    assert AuditEvent.objects.filter(action="activation.released_auto").count() == 1


def test_batches(make: Any, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.activation.domain import autorelease

    monkeypatch.setattr(autorelease, "BATCH", 2)
    for _ in range(5):
        make(last_seen_at=clock.now() - timedelta(days=DAYS + 1))
    assert release_stale_activations(now=clock.now()) == 5
    assert Activation.objects.filter(status="released_auto").count() == 5


def test_released_seat_is_free_for_a_new_activation(
    make: Any, licensed: Any, clock: FrozenClock
) -> None:
    from apps.activation.domain import license_usage

    licensed.limit = 1
    licensed.save()
    make(last_seen_at=clock.now() - timedelta(days=DAYS + 1))
    assert license_usage(licensed.id).active == 1
    release_stale_activations(now=clock.now())
    assert license_usage(licensed.id).active == 0


def test_task_kind_runs_through_the_queue(make: Any, clock: FrozenClock) -> None:
    row = make(last_seen_at=clock.now() - timedelta(days=DAYS + 1))
    enqueue("activation.release_stale", {}, now=clock.now())
    assert run_due(now=clock.now()) == 1
    row.refresh_from_db()
    assert row.status == "released_auto"


def test_hourly_schedule_and_worker(make: Any, clock: FrozenClock) -> None:
    from django.core.management import call_command

    from apps.outbox.models import Schedule, Task
    from infra.clock import use_clock

    row = make(last_seen_at=clock.now() - timedelta(days=DAYS + 1))
    with use_clock(clock):
        call_command("run_worker", "--once")
    schedule = Schedule.objects.get(name="activation.release_stale.hourly")
    assert schedule.cron == "5 * * * *"
    assert Task.objects.get(kind="activation.release_stale").status == "done"
    row.refresh_from_db()
    assert row.status == "released_auto"
    # The next slot is the next hour at :05.
    assert schedule.next_run_at == clock.now().replace(hour=9, minute=5, second=0)


def _offline_grace(days: int | None) -> None:
    from apps.catalog.models import PolicyProfile

    profile = PolicyProfile.objects.get(code="alteroffice-desktop.commercial")
    profile.params = profile.params | {"offline_grace_days": days}
    profile.save()


def test_offline_activation_keeps_its_seat_while_the_lease_lasts(
    make: Any, clock: FrozenClock
) -> None:
    """Question 39: an activation by files is released after its lease term, not before."""
    _offline_grace(90)
    offline = make(last_seen_at=clock.now() - timedelta(days=60), offline=True)
    online = make(last_seen_at=clock.now() - timedelta(days=60))
    assert release_stale_activations(now=clock.now()) == 1
    offline.refresh_from_db()
    online.refresh_from_db()
    assert (offline.status, online.status) == ("active", "released_auto")
    clock.advance(timedelta(days=30, seconds=1))
    assert release_stale_activations(now=clock.now()) == 1
    offline.refresh_from_db()
    assert offline.status == "released_auto"
    event = AuditEvent.objects.get(object_id=offline.external_id)
    assert event.data["offline"] is True


def test_offline_activation_uses_release_after_days_when_longer(
    make: Any, clock: FrozenClock
) -> None:
    _offline_grace(7)
    kept = make(last_seen_at=clock.now() - timedelta(days=DAYS - 1), offline=True)
    assert release_stale_activations(now=clock.now()) == 0
    kept.refresh_from_db()
    assert kept.status == "active"


def test_offline_activation_without_lease_term_is_not_released(
    make: Any, clock: FrozenClock
) -> None:
    _offline_grace(None)  # the lease does not expire: the seat stays until a release
    make(last_seen_at=clock.now() - timedelta(days=400), offline=True)
    assert release_stale_activations(now=clock.now()) == 0
