"""Automatic release of activations without contact (E12-02, prompt I4-03).

An active activation whose last contact is older than release_after_days of the policy profile
of its licence becomes released_auto; the product learns it from 410 activation_released at its
next check and activates again if a seat is free (section 5.4 of document 2). Rows are released
in batches of BATCH, each in its own transaction under the lock of the licence row (AGENTS.md,
rule 6), with an audit event per activation. A repeated run finds nothing to release.
"""

from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction

from apps.activation.domain.service import load_terms
from apps.activation.models import Activation, ActivationStatus
from apps.audit.domain import record
from apps.licensing.domain import lock_license

ACTOR = "system"
BATCH = 500
TASK_KIND = "activation.release_stale"


def _release_batch(license_id: UUID, now: datetime) -> int:
    with transaction.atomic():
        terms = load_terms(lock_license(license_id), now)
        cutoff = now - timedelta(days=terms.policy.release_after_days)
        rows = list(
            Activation.objects.select_for_update()
            .filter(license_id=license_id, status=ActivationStatus.ACTIVE, last_seen_at__lt=cutoff)
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
                data={"license_id": str(license_id), "last_seen_at": row.last_seen_at.isoformat()},
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
