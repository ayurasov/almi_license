"""Catalog rows of a local server, made from its package (E09-03).

A local server has no catalog of its own: products, editions and metrics are created by code as
the package names them, and every licence gets its own profile row with the full policy of the
package (code pkg.<license_id>, the version of the central profile).
"""

from typing import Any
from uuid import UUID

from apps.catalog.models import Edition, Metric, PolicyProfile, Product, SubjectType

SUBJECT_BY_METRIC = {
    "device": SubjectType.DEVICE,
    "server_instance": SubjectType.SERVER_INSTANCE,
    "os_node": SubjectType.OS_NODE,
}


def package_product(
    code: str, metric: str, edition: str | None, *, created_at: Any
) -> tuple[UUID, UUID | None, UUID]:
    metric_row, _ = Metric.objects.get_or_create(code=metric)
    product, _ = Product.objects.get_or_create(
        code=code,
        defaults={
            "default_metric": metric_row,
            "subject_type": SUBJECT_BY_METRIC.get(metric, SubjectType.DEVICE),
            "created_at": created_at,
        },
    )
    edition_id = None
    if edition is not None:
        edition_id = Edition.objects.get_or_create(product=product, code=edition)[0].id
    return product.id, edition_id, metric_row.id


def package_profile_code(license_id: UUID) -> str:
    return f"pkg.{license_id}"


def save_package_profile(
    license_id: UUID, version: int, params: dict[str, Any], *, created_at: Any
) -> str:
    """One row per licence: the package replaces the profile as a whole."""
    code = package_profile_code(license_id)
    PolicyProfile.objects.filter(code=code).delete()
    PolicyProfile.objects.create(
        code=code, version=max(version, 1), params=params, created_at=created_at
    )
    return code
