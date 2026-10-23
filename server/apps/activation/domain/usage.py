"""Seats of a license for the console (E07-04, E07-05, E10-01) and operator release (E03-05)."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max, Q

from apps.activation.models import Activation, ActivationStatus
from apps.audit.domain import record
from apps.licensing.domain import lock_license
from infra.errors import DomainError

ORDERINGS = frozenset({"last_seen_at", "-last_seen_at", "activated_at", "-activated_at"})
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Usage:
    active: int
    in_reserve: int
    released_auto: int
    conflicts: int
    last_seen_at: datetime | None
    by_version: dict[str, int]
    by_os: dict[str, int]


@dataclass(frozen=True)
class ActivationData:
    activation_id: str
    license_id: UUID
    instance_id: UUID
    instance_name: str
    subject_type: str
    status: str
    in_reserve: bool
    product_version: str
    os: dict[str, Any]
    activated_at: datetime
    last_seen_at: datetime
    released_at: datetime | None


def license_usage(license_id: UUID) -> Usage:
    rows = Activation.objects.filter(license_id=license_id)
    active = rows.filter(status=ActivationStatus.ACTIVE)
    versions = Counter(active.values_list("product_version", flat=True))
    systems = Counter(
        f"{os.get('name', '')} {os.get('version', '')}".strip()
        for os in active.values_list("os", flat=True)
    )
    return Usage(
        active=active.count(),
        in_reserve=active.filter(in_reserve=True).count(),
        released_auto=rows.filter(status=ActivationStatus.RELEASED_AUTO).count(),
        conflicts=rows.filter(status=ActivationStatus.CONFLICT).count(),
        last_seen_at=active.aggregate(last=Max("last_seen_at"))["last"],
        by_version=dict(versions),
        by_os=dict(systems),
    )


def _data(row: Activation) -> ActivationData:
    return ActivationData(
        activation_id=row.external_id,
        license_id=row.license_id,
        instance_id=row.instance_id,
        instance_name=row.instance_name,
        subject_type=row.subject_type,
        status=row.status,
        in_reserve=row.in_reserve,
        product_version=row.product_version,
        os=row.os,
        activated_at=row.activated_at,
        last_seen_at=row.last_seen_at,
        released_at=row.released_at,
    )


def list_activations(
    *,
    license_id: UUID | None = None,
    search: str = "",
    status: str = "",
    ordering: str = "-last_seen_at",
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, list[ActivationData]]:
    """search: activation_id, instance name or product version (E07-05)."""
    if ordering not in ORDERINGS or not 1 <= page_size <= MAX_PAGE_SIZE or page < 1:
        raise DomainError("invalid_request", "bad list parameters", data={"fields": {}})
    if status and status not in ActivationStatus.values:
        raise DomainError(
            "invalid_request", "bad status", data={"fields": {"status": ["Недопустимое значение."]}}
        )
    rows = Activation.objects.all()
    if license_id:
        rows = rows.filter(license_id=license_id)
    if status:
        rows = rows.filter(status=status)
    if search:
        rows = rows.filter(
            Q(external_id__iexact=search)
            | Q(instance_name__icontains=search)
            | Q(product_version__startswith=search)
        )
    rows = rows.order_by(ordering, "id")
    start = (page - 1) * page_size
    return rows.count(), [_data(r) for r in rows[start : start + page_size]]


def release_by_operator(
    activation_id: str, *, reason: str, actor: str, now: datetime, ip: str | None = None
) -> ActivationData:
    """Manual release (E07-05): the seat is freed; the product gets 410 at the next check."""
    text = reason.strip()
    if not text:
        raise DomainError(
            "invalid_request", "reason", data={"fields": {"reason": ["Укажите причину."]}}
        )
    license_id = (
        Activation.objects.filter(external_id=activation_id)
        .values_list("license_id", flat=True)
        .first()
    )
    if license_id is None:
        raise DomainError("invalid_request", "activation not found")
    with transaction.atomic():
        lock_license(license_id)
        row = Activation.objects.select_for_update().get(external_id=activation_id)
        if row.status != ActivationStatus.ACTIVE:
            raise DomainError(
                "invalid_request",
                "not active",
                data={"fields": {"status": ["Активация уже не занимает место."]}},
            )
        row.status = ActivationStatus.RELEASED
        row.released_at = now
        row.save(update_fields=["status", "released_at"])
        record(
            actor,
            "activation.released",
            "activation",
            activation_id,
            at=now,
            ip=ip,
            data={"reason": text},
        )
    return _data(row)
