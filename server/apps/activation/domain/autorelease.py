"""Automatic release of activations without contact (E12-02, prompt I4-03).

An active activation whose last contact is older than release_after_days of the policy profile
of its licence becomes released_auto. An activation by files (last contact by .alk-req) holds a
lease for offline_grace_days without contact, so it is released only after
max(release_after_days, offline_grace_days), and never when the lease has no term (question 39).
The product learns of the release from 410 activation_released at its next check and
activates again if a seat is free (section 5.4 of document 2). Rows are released
in batches of BATCH, each in its own transaction under the lock of the licence row (AGENTS.md,
rule 6), with an audit event per activation. A repeated run finds nothing to release.
"""

from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Q

from apps.activation.domain.service import load_terms
from apps.activation.models import Activation, ActivationStatus
from apps.audit.domain import record
from apps.licensing.domain import lock_license

ACTOR = "system"
BATCH = 500
TASK_KIND = "activation.release_stale"


def _release_batch(license_id: UUID, now: datetime) -> int:
    with transaction.atomic():
        policy = load_terms(lock_license(license_id), now).policy
        stale = Q(offline=False, last_seen_at__lt=now - timedelta(days=policy.release_after_days))
        if policy.offline_grace_days is not None:
            days = max(policy.release_after_days, policy.offline_grace_days)
            stale |= Q(offline=True, last_seen_at__lt=now - timedelta(days=days))
        rows = list(
            Activation.objects.select_for_update()
            .filter(stale, license_id=license_id, status=ActivationStatus.ACTIVE)
            .order_by("last_seen_at")[:BATCH]
        )
        for row in rows:
            row.status = ActivationStatus.RELEASED_AUTO
            row.released_at = now
            row.save(update_fields=["status", "released_at"])
            record(
                ACTOR,
                "activation.released_auto",
                "activation",
                row.external_id,
                at=now,
                data={
                    "license_id": str(license_id),
                    "last_seen_at": row.last_seen_at.isoformat(),
                    "offline": row.offline,
                },
            )
    return len(rows)


def release_stale_activations(*, now: datetime) -> int:
    """Release every stale activation; returns how many were released."""
    licenses = (
        Activation.objects.filter(status=ActivationStatus.ACTIVE)
        .values_list("license_id", flat=True)
        .distinct()
    )
    released = 0
    for license_id in list(licenses):
        while count := _release_batch(license_id, now):
            released += count
            if count < BATCH:
                break
    return released


def run_release_task(payload: dict[str, object], now: datetime) -> None:
    """Handler of TASK_KIND in the outbox queue."""
    release_stale_activations(now=now)
