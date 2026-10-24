"""Domain services of the catalog module: products, editions, capabilities, policy profiles."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from apps.catalog.models import (
    Capability,
    CapabilityStatus,
    Edition,
    Metric,
    PolicyProfile,
    Product,
)


@dataclass(frozen=True)
class ProductInfo:
    id: UUID
    code: str
    default_profile_code: str


@dataclass(frozen=True)
class ProfileVersion:
    code: str
    version: int
    params: dict[str, Any]


class ProfileNotFound(LookupError):
    pass


def product_info(product_id: UUID) -> ProductInfo:
    row = Product.objects.get(id=product_id)
    return ProductInfo(id=row.id, code=row.code, default_profile_code=row.default_profile_code)


def edition_code(edition_id: UUID | None) -> str | None:
    if edition_id is None:
        return None
    code: str = Edition.objects.values_list("code", flat=True).get(id=edition_id)
    return code


def metric_code(metric_id: UUID) -> str:
    code: str = Metric.objects.values_list("code", flat=True).get(id=metric_id)
    return code


def capabilities(product_id: UUID, edition_id: UUID | None) -> frozenset[str]:
    """Active capabilities of the edition; without an edition — all active ones of the product."""
    rows = Capability.objects.filter(product_id=product_id, status=CapabilityStatus.ACTIVE)
    if edition_id is not None:
        rows = rows.filter(editions__id=edition_id)
    return frozenset(rows.values_list("code", flat=True))


def latest_profile(code: str) -> ProfileVersion:
    row = PolicyProfile.objects.filter(code=code).order_by("-version").first()
    if row is None:
        raise ProfileNotFound(code)
    return ProfileVersion(code=row.code, version=row.version, params=dict(row.params))


def list_products() -> list[dict[str, Any]]:
    """Products with editions and metrics for console selects (E07-04)."""
    metrics = {m.id: m.code for m in Metric.objects.all()}
    result = []
    for product in Product.objects.prefetch_related("editions").order_by("code"):
        result.append(
            {
                "id": product.id,
                "code": product.code,
                "name": product.name,
                "default_metric_id": product.default_metric_id,
                "default_metric": metrics.get(product.default_metric_id, ""),
                "editions": [
                    {"id": e.id, "code": e.code, "name": e.name} for e in product.editions.all()
                ],
            }
        )
    return result


from apps.catalog.domain.admin import (  # noqa: E402  (admin services use the models above)
    add_capability,
    create_metric,
    create_product,
    list_metrics,
    list_profiles,
    product_details,
    profile_versions,
    save_edition,
    save_profile,
    update_capability,
    update_product,
)

__all__ = [
    "add_capability",
    "create_metric",
    "create_product",
    "list_metrics",
    "list_profiles",
    "product_details",
    "profile_versions",
    "save_edition",
    "save_profile",
    "update_capability",
    "update_product",
    "ProductInfo",
    "ProfileNotFound",
    "ProfileVersion",
    "capabilities",
    "edition_code",
    "latest_profile",
    "list_products",
    "metric_code",
    "product_info",
]
