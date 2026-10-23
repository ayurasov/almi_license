"""License lookup and locking for seat accounting (AGENTS.md, rule 6)."""

from dataclasses import dataclass
from datetime import datetime
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
    extra_capabilities: tuple[str, ...]
    customer_id: UUID
    customer_name: str


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
        extra_capabilities=tuple(row.extra_capabilities),
        customer_id=row.customer_id,
        customer_name=row.customer.name,
    )
