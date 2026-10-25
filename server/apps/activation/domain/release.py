"""Release of an activation by the product (E03-05; section 5.4 of document 2).

The seat is freed under the license lock; the product gets a receipt alm-receipt+jws. A repeated
call returns the same receipt. An activation released by the operator or automatically also gets
a receipt, so that a product that missed the 410 can finish its uninstall.
"""

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from apps.activation.domain.leases import rfc3339
from apps.activation.domain.service import ACTOR
from apps.activation.models import Activation, ActivationStatus
from apps.audit.domain import record
from apps.licensing.domain import lock_license
from apps.signing.domain import issue_jws
from infra.errors import DomainError

RECEIPT_TYP = "alm-receipt+jws"
REASONS = frozenset({"uninstall", "user", "transfer", "directive"})
RELEASED = (ActivationStatus.RELEASED, ActivationStatus.RELEASED_AUTO)


@dataclass(frozen=True)
class ReleaseResult:
    activation_id: str
    released_at: datetime
    receipt: str


def _receipt(activation: Activation, released_at: datetime, now: datetime) -> str:
    return issue_jws(
        RECEIPT_TYP,
        {
            "ver": 1,
            "type": "release",
            "iat": int(now.timestamp()),
            "activation_id": activation.external_id,
            "released_at": rfc3339(released_at),
        },
    )


def release(
    activation_id: str,
    *,
    reason: str,
    device_pubkey: str | None = None,
    now: datetime,
    ip: str | None = None,
) -> ReleaseResult:
    """device_pubkey, when given (offline files), must be the key the activation was made with."""
    if reason not in REASONS:
        raise DomainError("invalid_request", "unknown release reason")
    license_id = (
        Activation.objects.filter(external_id=activation_id)
        .exclude(status=ActivationStatus.CONFLICT)
        .values_list("license_id", flat=True)
        .first()
    )
    if license_id is None:
        raise DomainError("activation_not_found")
    with transaction.atomic():
        lock_license(license_id)
        row = Activation.objects.select_for_update().get(external_id=activation_id)
        if device_pubkey is not None and device_pubkey != row.device_pubkey:
            raise DomainError("signature_invalid")
        if row.release_receipt and row.released_at is not None:
            return ReleaseResult(row.external_id, row.released_at, row.release_receipt)
        released_at = row.released_at if row.status in RELEASED and row.released_at else now
        if row.status not in RELEASED:
            row.status = ActivationStatus.RELEASED
            record(
                ACTOR,
                "activation.released",
                "activation",
                row.external_id,
                at=now,
                ip=ip,
                data={"reason": reason, "by": "product"},
            )
        row.released_at = released_at
        row.release_receipt = _receipt(row, released_at, now)
        row.save(update_fields=["status", "released_at", "release_receipt"])
        return ReleaseResult(row.external_id, released_at, row.release_receipt)
