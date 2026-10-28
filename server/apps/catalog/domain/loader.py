"""Initial catalog from a fixture (E01-02; section 10 of document 4, table 8.2 of document 1).

Idempotent and additive: products, editions, capabilities and metrics are created when missing; a
product or an edition that exists keeps what the operator set in the console (names, default
profile, base capabilities). A policy profile gets a new version only for parameters it never had,
so a profile edited in the console is not put back to the fixture by the next run (E01-03). Every
run that changes something writes an audit event (AGENTS.md, rule 7).
"""

from datetime import datetime
from typing import Any

from django.db import transaction

from apps.audit.domain import record
from apps.catalog.models import Capability, Edition, Metric, PolicyProfile, Product


def load_catalog(
    document: dict[str, Any], *, now: datetime, actor: str = "system"
) -> dict[str, int]:
    counts = {"metrics": 0, "products": 0, "editions": 0, "capabilities": 0, "profile_versions": 0}
    created: dict[str, list[str]] = {"products": [], "editions": [], "profiles": []}
    with transaction.atomic():
        for item in document.get("metrics", []):
            Metric.objects.get_or_create(code=item["code"], defaults={"name": item.get("name", {})})
            counts["metrics"] += 1
        for item in document["products"]:
            metric, _ = Metric.objects.get_or_create(code=item["metric"])
            product, new_product = Product.objects.get_or_create(
                code=item["code"],
                defaults={
                    "name": item.get("name", {}),
                    "default_metric": metric,
                    "subject_type": item["subject_type"],
                    "default_profile_code": item.get("default_profile", ""),
                    "created_at": now,
                },
            )
            counts["products"] += 1
            if new_product:
                created["products"].append(product.code)
            for edition_item in item.get("editions", []):
                edition, new_edition = Edition.objects.get_or_create(
                    product=product, code=edition_item["code"]
                )
                counts["editions"] += 1
                if not new_edition:
                    continue
                created["editions"].append(f"{product.code}.{edition.code}")
                capabilities = []
                for code in edition_item.get("base_capabilities", []):
                    capability, new_capability = Capability.objects.get_or_create(
                        product=product, code=code
                    )
                    counts["capabilities"] += int(new_capability)
                    capabilities.append(capability)
                edition.base_capabilities.set(capabilities)
        for item in document.get("profiles", []):
            params = {key: value for key, value in item.items() if key != "code"}
            versions = PolicyProfile.objects.select_for_update().filter(code=item["code"])
            if any(row.params == params for row in versions):
                continue
            latest = versions.order_by("-version").first()
            PolicyProfile.objects.create(
                code=item["code"],
                version=1 if latest is None else latest.version + 1,
                params=params,
                created_at=now,
            )
            counts["profile_versions"] += 1
            created["profiles"].append(item["code"])
        if any(created.values()) or counts["capabilities"]:
            record(actor, "catalog.loaded", "catalog", "fixture", at=now, data=created)
    return counts
