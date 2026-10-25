"""License lookup and locking for seat accounting (AGENTS.md, rule 6)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.licensing.models import License, LicenseKey


@dataclass(frozen=True)
class LicenseRecord:
    id: UUID
    product_id: UUID
    edition_id: UUID | None
    type: str
    status: str
    limit: int
    reserve_pct: int | None
    valid_from: datetime
    valid_until: datetime | None
    support_until: datetime | None
    policy_profile_code: str
    enforcement: str
    monitor_until: datetime | None
    extra_capabilities: tuple[str, ...]
    customer_id: UUID
    customer_name: str
    metric_id: UUID | None = None
    updated_at: datetime | None = None
    limits: dict[str, Any] = field(default_factory=dict)
    state: str = ""


def _record(row: License) -> LicenseRecord:
    return LicenseRecord(
        id=row.id,
        product_id=row.product_id,
        edition_id=row.edition_id,
        type=row.type,
        status=row.status,
        limit=row.limit,
        reserve_pct=row.reserve_pct,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        support_until=row.support_until,
        policy_profile_code=row.policy_profile_code,
        enforcement=row.enforcement,
        monitor_until=row.monitor_until,
        extra_capabilities=tuple(row.extra_capabilities),
        customer_id=row.customer_id,
        customer_name=row.customer.name,
        metric_id=row.metric_id,
        updated_at=row.updated_at,
        limits=dict(row.limits),
        state=row.state,
    )


def license_records(license_ids: list[UUID]) -> list[LicenseRecord]:
    """Licenses without a lock, for snapshots such as a local server package (E09-02)."""
    rows = License.objects.select_related("customer").filter(id__in=license_ids).order_by("id")
    return [_record(row) for row in rows]


@dataclass(frozen=True)
class KeyRecord:
    key_hash: str
    key_mask: str
    license_id: UUID


def keys_of(license_ids: list[UUID]) -> list[KeyRecord]:
    rows = LicenseKey.objects.filter(license_id__in=license_ids).order_by("key_hash")
    return [KeyRecord(r.key_hash, r.key_mask, r.license_id) for r in rows]


def license_id_by_key_hash(key_hash: str) -> UUID | None:
    """One query whether or not the key exists (no timing difference, prompt I2-04)."""
    return LicenseKey.objects.filter(key_hash=key_hash).values_list("license_id", flat=True).first()


def lock_license(license_id: UUID) -> LicenseRecord:
    """SELECT … FOR UPDATE of the license row; call inside transaction.atomic()."""
    row = (
        License.objects.select_for_update(of=("self",))
        .select_related("customer")
        .get(id=license_id)
    )
    return _record(row)


def counts_active_only(limits: dict[str, Any]) -> bool:
    """Users of a server product are counted active only (lease limits.only_count_active)."""
    default = "active_users" in limits and "named_users" not in limits
    return bool(limits.get("only_count_active", default))


def license_ids(*, batch: int = 1000) -> list[list[UUID]]:
    """Ids of all licences in batches (background recalculation, E12-03)."""
    ids = list(License.objects.order_by("id").values_list("id", flat=True))
    return [ids[i : i + batch] for i in range(0, len(ids), batch)]


def save_states(states: dict[UUID, str], *, at: datetime) -> None:
    """Computed states of licences; not a change of rights (no rights_version, no audit)."""
    rows = list(License.objects.filter(id__in=list(states)))
    for row in rows:
        row.state = states[row.id]
        row.state_at = at
    License.objects.bulk_update(rows, ["state", "state_at"])
