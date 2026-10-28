"""Catalog administration (E01-02) and versioned policy profiles (E01-03).

A profile is never changed in place: every save is a new version (code + version unique);
licenses and products refer to the code and get the latest version with the next lease.
"""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.domain import record
from apps.catalog.models import (
    Capability,
    CapabilityStatus,
    Edition,
    Metric,
    PolicyProfile,
    Product,
    ProductStatus,
)
from apps.policy.domain import profile_errors
from infra.errors import DomainError

PROFILE_CODE = re.compile(r"[a-z0-9-]{2,64}\.[a-z0-9_-]{2,32}")
PRODUCT_CODE = re.compile(r"[a-z0-9-]{2,64}")
EDITION_CODE = re.compile(r"[a-z0-9-]{2,32}")
CAPABILITY_CODE = re.compile(r"[a-z0-9_]{2,48}|app:[a-z0-9_-]{1,44}")


def _invalid(fields: dict[str, list[str]]) -> DomainError:
    return DomainError("invalid_request", "catalog fields are invalid", data={"fields": fields})


def _names(value: Any) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or not all(isinstance(v, str) for v in value.values())
        or not value.get("ru")
    ):
        raise _invalid({"name": ["Укажите название (ru)."]})
    return dict(value)


def _locked_product(product_id: UUID) -> Product:
    product = Product.objects.select_for_update().filter(id=product_id).first()
    if product is None:
        raise DomainError("not_found", "product not found")
    return product


def product_details(product_id: UUID) -> dict[str, Any]:
    product = (
        Product.objects.prefetch_related("editions__base_capabilities", "capabilities")
        .filter(id=product_id)
        .first()
    )
    if product is None:
        raise DomainError("not_found", "product not found")
    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "status": product.status,
        "subject_type": product.subject_type,
        "default_metric_id": product.default_metric_id,
        "default_profile_code": product.default_profile_code,
        "capabilities": [
            {"id": c.id, "code": c.code, "name": c.name, "status": c.status}
            for c in sorted(product.capabilities.all(), key=lambda c: c.code)
        ],
        "editions": [
            {
                "id": e.id,
                "code": e.code,
                "name": e.name,
                "base_capabilities": sorted(c.code for c in e.base_capabilities.all()),
            }
            for e in sorted(product.editions.all(), key=lambda e: e.code)
        ],
    }


def list_metrics() -> list[dict[str, Any]]:
    return [{"id": m.id, "code": m.code, "name": m.name} for m in Metric.objects.order_by("code")]


def create_metric(
    values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    code = str(values.get("code", ""))
    if not CAPABILITY_CODE.fullmatch(code) or code.startswith("app:"):
        raise _invalid({"code": ["Латиница в нижнем регистре, цифры и _, 2–32 символа."]})
    with transaction.atomic():
        if Metric.objects.filter(code=code).exists():
            raise _invalid({"code": ["Метрика с таким кодом уже есть."]})
        metric = Metric.objects.create(code=code, name=_names(values.get("name")))
        record(actor, "catalog.metric_created", "metric", code, at=now, ip=ip)
    return {"id": metric.id, "code": metric.code, "name": metric.name}


def create_product(
    values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    code = str(values.get("code", ""))
    if not PRODUCT_CODE.fullmatch(code):
        errors["code"] = ["Латиница в нижнем регистре, цифры и дефис, 2–64 символа."]
    elif Product.objects.filter(code=code).exists():
        errors["code"] = ["Продукт с таким кодом уже есть."]
    metric_id = values.get("default_metric_id")
    metric = Metric.objects.filter(id=metric_id).first() if metric_id else None
    if metric is None:
        errors["default_metric_id"] = ["Выберите метрику."]
    if values.get("subject_type") not in ("device", "server_instance", "os_node"):
        errors["subject_type"] = ["Недопустимое значение."]
    if errors or metric is None:
        raise _invalid(errors)
    with transaction.atomic():
        product = Product.objects.create(
            code=code,
            name=_names(values.get("name")),
            default_metric=metric,
            subject_type=values["subject_type"],
            default_profile_code=str(values.get("default_profile_code", "")),
            created_at=now,
        )
        record(actor, "catalog.product_created", "product", code, at=now, ip=ip)
    return product_details(product.id)


def update_product(
    product_id: UUID, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    with transaction.atomic():
        product = _locked_product(product_id)
        if "name" in values:
            product.name = _names(values["name"])
        if "status" in values:
            if values["status"] not in ProductStatus.values:
                raise _invalid({"status": ["Недопустимое значение."]})
            product.status = values["status"]
        if "default_profile_code" in values:
            code = str(values["default_profile_code"])
            if code and not PolicyProfile.objects.filter(code=code).exists():
                raise _invalid({"default_profile_code": ["Профиль не найден."]})
            product.default_profile_code = code
        product.save()
        record(
            actor,
            "catalog.product_updated",
            "product",
            product.code,
            at=now,
            ip=ip,
            data={k: str(v) for k, v in values.items()},
        )
    return product_details(product_id)


def add_capability(
    product_id: UUID, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    code = str(values.get("code", ""))
    if not CAPABILITY_CODE.fullmatch(code):
        raise _invalid({"code": ["Код функции: латиница, цифры и _, или app:<имя>."]})
    with transaction.atomic():
        product = _locked_product(product_id)
        if Capability.objects.filter(product=product, code=code).exists():
            raise _invalid({"code": ["Такая функция уже есть."]})
        Capability.objects.create(product=product, code=code, name=values.get("name", {}))
        record(
            actor,
            "catalog.capability_added",
            "product",
            product.code,
            at=now,
            ip=ip,
            data={"code": code},
        )
    return product_details(product_id)


def update_capability(
    product_id: UUID,
    code: str,
    values: dict[str, Any],
    *,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> dict[str, Any]:
    """Name or status; a deprecated function leaves leases at the next check (document 4, s. 4)."""
    with transaction.atomic():
        row = (
            Capability.objects.select_for_update().filter(product_id=product_id, code=code).first()
        )
        if row is None:
            raise DomainError("not_found", "capability not found")
        if "name" in values:
            row.name = values["name"]
        if "status" in values:
            if values["status"] not in CapabilityStatus.values:
                raise _invalid({"status": ["Недопустимое значение."]})
            row.status = values["status"]
        row.save()
        record(
            actor,
            "catalog.capability_updated",
            "product",
            row.product.code,
            at=now,
            ip=ip,
            data={"code": code, **{k: str(v) for k, v in values.items()}},
        )
    return product_details(product_id)


def save_edition(
    product_id: UUID, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    """Create or update an edition by code; base_capabilities — codes of the product's functions."""
    code = str(values.get("code", ""))
    if not EDITION_CODE.fullmatch(code):
        raise _invalid({"code": ["Латиница в нижнем регистре, цифры и дефис, 2–32 символа."]})
    with transaction.atomic():
        product = _locked_product(product_id)
        wanted = set(values.get("base_capabilities", []))
        capabilities = list(Capability.objects.filter(product=product, code__in=wanted))
        unknown = wanted - {c.code for c in capabilities}
        if unknown:
            raise _invalid({"base_capabilities": [f"Нет функций: {', '.join(sorted(unknown))}."]})
        edition, _ = Edition.objects.get_or_create(product=product, code=code)
        if "name" in values:
            edition.name = values["name"]
            edition.save()
        edition.base_capabilities.set(capabilities)
        record(
            actor,
            "catalog.edition_saved",
            "product",
            product.code,
            at=now,
            ip=ip,
            data={"edition": code, "capabilities": sorted(wanted)},
        )
    return product_details(product_id)


def _profile(row: PolicyProfile) -> dict[str, Any]:
    return {
        "code": row.code,
        "version": row.version,
        "params": row.params,
        "created_at": row.created_at,
    }


def list_profiles() -> list[dict[str, Any]]:
    """The latest version of every profile code."""
    latest: dict[str, PolicyProfile] = {}
    for row in PolicyProfile.objects.order_by("code", "version"):
        latest[row.code] = row
    return [_profile(row) for row in latest.values()]


def profile_versions(code: str) -> list[dict[str, Any]]:
    rows = PolicyProfile.objects.filter(code=code).order_by("-version")
    if not rows.exists():
        raise DomainError("not_found", "profile not found")
    return [_profile(row) for row in rows]


def save_profile(
    code: str, params: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> dict[str, Any]:
    """A new version of the profile (version 1 for a new code); unchanged params add nothing."""
    if not PROFILE_CODE.fullmatch(code):
        raise _invalid(
            {"code": ["Код профиля: <продукт>.<класс>, например alteroffice-desktop.commercial."]}
        )
    errors = profile_errors(params)
    if errors:
        raise _invalid(errors)
    with transaction.atomic():
        latest = (
            PolicyProfile.objects.select_for_update().filter(code=code).order_by("-version").first()
        )
        if latest is not None and latest.params == params:
            return _profile(latest)
        row = PolicyProfile.objects.create(
            code=code,
            version=1 if latest is None else latest.version + 1,
            params=params,
            created_at=now,
        )
        record(
            actor,
            "catalog.profile_version",
            "profile",
            code,
            at=now,
            ip=ip,
            data={"version": row.version},
        )
    return _profile(row)
