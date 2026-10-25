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
    offline: bool = False


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


def usage_by_license(license_ids: list[UUID]) -> dict[UUID, Usage]:
    """license_usage for many licences with a fixed number of queries (E10-01)."""
    rows = Activation.objects.filter(license_id__in=license_ids).values(
        "license_id", "status", "in_reserve", "product_version", "os", "last_seen_at"
    )
    counts: dict[UUID, dict[str, Any]] = {
        lid: {
            "active": 0,
            "reserve": 0,
            "auto": 0,
            "conflicts": 0,
            "last": None,
            "versions": Counter(),
            "systems": Counter(),
        }
        for lid in license_ids
    }
    for row in rows:
        item = counts[row["license_id"]]
        if row["status"] == ActivationStatus.ACTIVE:
            item["active"] += 1
            item["reserve"] += int(row["in_reserve"])
            item["versions"][row["product_version"]] += 1
            os = row["os"] or {}
            item["systems"][f"{os.get('name', '')} {os.get('version', '')}".strip()] += 1
            if item["last"] is None or row["last_seen_at"] > item["last"]:
                item["last"] = row["last_seen_at"]
        elif row["status"] == ActivationStatus.RELEASED_AUTO:
            item["auto"] += 1
        elif row["status"] == ActivationStatus.CONFLICT:
            item["conflicts"] += 1
    return {
        lid: Usage(
            active=c["active"],
            in_reserve=c["reserve"],
            released_auto=c["auto"],
            conflicts=c["conflicts"],
            last_seen_at=c["last"],
            by_version=dict(c["versions"]),
            by_os=dict(c["systems"]),
        )
        for lid, c in counts.items()
    }


def activations_of(license_ids: list[UUID], *, limit: int = 100_000) -> list[ActivationData]:
    """Activations of the licences for the export sheet (E10-02), newest contact first."""
    rows = Activation.objects.filter(license_id__in=license_ids).order_by("-last_seen_at", "id")
    return [_data(r) for r in rows[:limit]]


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
        offline=row.offline,
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
        raise DomainError("not_found", "activation not found")
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


def revoke_activations(activation_ids: list[str], *, now: datetime) -> int:
    """Activations revoked by the package of a local server (E09-03); their next check gets 403."""
    rows = Activation.objects.filter(external_id__in=activation_ids, status=ActivationStatus.ACTIVE)
    count = 0
    for row in rows:
        row.status = ActivationStatus.REVOKED
        row.save(update_fields=["status"])
        record("package", "activation.revoked", "activation", row.external_id, at=now)
        count += 1
    return count


def instance_activation(license_id: UUID, instance_id: UUID) -> tuple[str, int] | None:
    """(activation_id, lease_seq) of the active activation of an instance (compat adapters)."""
    row = (
        Activation.objects.filter(
            license_id=license_id, instance_id=instance_id, status=ActivationStatus.ACTIVE
        )
        .values_list("external_id", "lease_seq")
        .first()
    )
    return None if row is None else (row[0], row[1])


def active_activation_ids(license_ids: list[UUID]) -> dict[UUID, list[str]]:
    """external_id of the active activations of each licence (statistics of users, E11-02)."""
    result: dict[UUID, list[str]] = {license_id: [] for license_id in license_ids}
    rows = Activation.objects.filter(license_id__in=license_ids, status=ActivationStatus.ACTIVE)
    for license_id, external_id in rows.values_list("license_id", "external_id"):
        result[license_id].append(external_id)
    return result


def customer_objects(license_ids: list[UUID]) -> frozenset[tuple[str, str]]:
    """Audit objects of a customer: its licences and their activations (E10-04, E07-08)."""
    activations = Activation.objects.filter(license_id__in=license_ids).values_list(
        "external_id", flat=True
    )
    return frozenset(
        [("license", str(license_id)) for license_id in license_ids]
        + [("activation", external_id) for external_id in activations]
    )


def released_between(license_ids: list[UUID], since: datetime, until: datetime) -> dict[UUID, int]:
    """Activations released (by the product, the operator or automatically) in [since, until)."""
    result = dict.fromkeys(license_ids, 0)
    rows = Activation.objects.filter(
        license_id__in=license_ids,
        status__in=(ActivationStatus.RELEASED, ActivationStatus.RELEASED_AUTO),
        released_at__gte=since,
        released_at__lt=until,
    )
    for license_id in rows.values_list("license_id", flat=True):
        result[license_id] += 1
    return result
