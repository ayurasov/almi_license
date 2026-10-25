"""Initial catalog from a fixture (E01-02; section 10 of document 4, table 8.2 of document 1).

Idempotent: products, editions, capabilities and metrics are created or updated by code; a policy
profile gets a new version only when its parameters differ from the latest one (E01-03).
"""

from datetime import datetime
from typing import Any

from django.db import transaction

from apps.catalog.models import Capability, Edition, Metric, PolicyProfile, Product


def load_catalog(document: dict[str, Any], *, now: datetime) -> dict[str, int]:
    counts = {"metrics": 0, "products": 0, "editions": 0, "capabilities": 0, "profile_versions": 0}
    with transaction.atomic():
        for item in document.get("metrics", []):
            Metric.objects.update_or_create(
                code=item["code"], defaults={"name": item.get("name", {})}
            )
            counts["metrics"] += 1
        for item in document["products"]:
            metric, _ = Metric.objects.get_or_create(code=item["metric"])
            product, _ = Product.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item.get("name", {}),
                    "default_metric": metric,
                    "subject_type": item["subject_type"],
                    "default_profile_code": item.get("default_profile", ""),
                },
                create_defaults={
                    "name": item.get("name", {}),
                    "default_metric": metric,
                    "subject_type": item["subject_type"],
                    "default_profile_code": item.get("default_profile", ""),
                    "created_at": now,
                },
            )
            counts["products"] += 1
            for edition_item in item.get("editions", []):
                edition, _ = Edition.objects.get_or_create(
                    product=product, code=edition_item["code"]
                )
                capabilities = []
                for code in edition_item.get("base_capabilities", []):
                    capability, created = Capability.objects.get_or_create(
                        product=product, code=code
                    )
                    counts["capabilities"] += int(created)
                    capabilities.append(capability)
                edition.base_capabilities.set(capabilities)
                counts["editions"] += 1
        for item in document.get("profiles", []):
            params = {key: value for key, value in item.items() if key != "code"}
            latest = PolicyProfile.objects.filter(code=item["code"]).order_by("-version").first()
            if latest is None or latest.params != params:
                PolicyProfile.objects.create(
                    code=item["code"],
                    version=1 if latest is None else latest.version + 1,
                    params=params,
                    created_at=now,
                )
                counts["profile_versions"] += 1
    return counts
