"""Licences of a local server from its package (E09-03): a full snapshot replaces the previous one.

Licences that left the package are suspended (their seats went back to the central server or to
another server) and may come back with a later package; keys follow their licences.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.licensing.models import Customer, KeyFormat, License, LicenseKey, LicenseStatus


@dataclass(frozen=True)
class PackageLicense:
    license_id: UUID
    product_id: UUID
    edition_id: UUID | None
    metric_id: UUID
    type: str
    seats: int
    valid_from: datetime
    valid_until: datetime | None
    support_until: datetime | None
    status: str
    capabilities: list[str]
    profile_code: str
    reserve_pct: int | None
    limits: dict[str, Any] = field(default_factory=dict)


def replace_package_licenses(
    customer: dict[str, Any],
    licenses: list[PackageLicense],
    keys: list[dict[str, Any]],
    *,
    now: datetime,
) -> None:
    """Call inside the transaction of the package import; licence rows are locked first."""
    customer_id = UUID(str(customer["id"]))
    Customer.objects.update_or_create(
        id=customer_id,
        defaults={"name": customer.get("name") or str(customer_id)},
        create_defaults={
            "name": customer.get("name") or str(customer_id),
            "created_at": now,
        },
    )
    wanted = {item.license_id for item in licenses}
    list(License.objects.select_for_update().filter(customer_id=customer_id))
    for item in licenses:
        License.objects.update_or_create(
            id=item.license_id,
            defaults={
                "customer_id": customer_id,
                "product_id": item.product_id,
                "edition_id": item.edition_id,
                "metric_id": item.metric_id,
                "type": item.type,
                "limit": item.seats,
                "reserve_pct": item.reserve_pct,
                "valid_from": item.valid_from,
                "valid_until": item.valid_until,
                "support_until": item.support_until,
                "status": item.status,
                "policy_profile_code": item.profile_code,
                "enforcement": "",
                "extra_capabilities": sorted(item.capabilities),
                "limits": item.limits,
                "updated_at": now,
            },
            create_defaults={
                "customer_id": customer_id,
                "product_id": item.product_id,
                "edition_id": item.edition_id,
                "metric_id": item.metric_id,
                "type": item.type,
                "limit": item.seats,
                "reserve_pct": item.reserve_pct,
                "valid_from": item.valid_from,
                "valid_until": item.valid_until,
                "support_until": item.support_until,
                "status": item.status,
                "policy_profile_code": item.profile_code,
                "extra_capabilities": sorted(item.capabilities),
                "limits": item.limits,
                "created_at": now,
                "updated_at": now,
            },
        )
    License.objects.exclude(id__in=wanted).exclude(status=LicenseStatus.REVOKED).update(
        status=LicenseStatus.SUSPENDED, updated_at=now
    )
    hashes = {k["key_hash"] for k in keys}
    LicenseKey.objects.exclude(key_hash__in=hashes).delete()
    for key in keys:
        LicenseKey.objects.update_or_create(
            key_hash=key["key_hash"],
            defaults={"license_id": UUID(str(key["license_id"])), "key_mask": key["key_mask"]},
            create_defaults={
                "license_id": UUID(str(key["license_id"])),
                "key_mask": key["key_mask"],
                "format": KeyFormat.V1,
            },
        )
