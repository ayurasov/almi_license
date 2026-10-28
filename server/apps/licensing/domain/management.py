"""Operator actions on licenses (E01-05, E01-06, E01-07, E01-08).

Every change runs in a transaction with SELECT … FOR UPDATE of the license row and writes an
audit event (AGENTS.md, rules 6 and 7). Renewal and lifting a block raise rights_version.
"""

import re
import string
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.domain import record
from apps.licensing.domain.keys import key_hash, key_mask, normalize_key
from apps.licensing.models import (
    Customer,
    Enforcement,
    License,
    LicenseKey,
    LicenseStatus,
    LicenseType,
)
from infra.crypto.random import random_text
from infra.errors import DomainError

ORDERINGS = frozenset(
    {"valid_until", "-valid_until", "created_at", "-created_at", "status", "-status"}
)
MAX_PAGE_SIZE = 100
# Key alphabet: digits and Latin capitals without I and O, which are read as 1 and 0.
KEY_ALPHABET = "".join(c for c in string.digits + string.ascii_uppercase if c not in "IO")


@dataclass(frozen=True)
class LicenseData:
    id: UUID
    customer_id: UUID
    customer_name: str
    product_id: UUID
    edition_id: UUID | None
    type: str
    status: str
    limit: int
    reserve_pct: int | None
    valid_from: datetime
    valid_until: datetime | None
    support_until: datetime | None
    enforcement: str
    monitor_until: datetime | None
    policy_profile_code: str
    rights_version: int
    key_masks: list[str] = field(default_factory=list)
    limits: dict[str, Any] = field(default_factory=dict)
    state: str = ""
    state_at: datetime | None = None
    max_product_version: str = ""


@dataclass(frozen=True)
class LicensePage:
    count: int
    results: list[LicenseData]


@dataclass(frozen=True)
class IssuedKey:
    """The full key is returned once and never stored (E01-06)."""

    license_id: UUID
    key: str = field(repr=False)
    key_mask: str = ""


def _invalid(
    fields: dict[str, list[str]], detail: str = "license fields are invalid"
) -> DomainError:
    return DomainError("invalid_request", detail, data={"fields": fields})


def _data(row: License) -> LicenseData:
    return LicenseData(
        id=row.id,
        customer_id=row.customer_id,
        customer_name=row.customer.name,
        product_id=row.product_id,
        edition_id=row.edition_id,
        type=row.type,
        status=row.status,
        limit=row.limit,
        reserve_pct=row.reserve_pct,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        support_until=row.support_until,
        enforcement=row.enforcement,
        monitor_until=row.monitor_until,
        policy_profile_code=row.policy_profile_code,
        rights_version=row.rights_version,
        key_masks=sorted(key.key_mask for key in row.keys.all()),
        limits=dict(row.limits),
        state=row.state,
        state_at=row.state_at,
        max_product_version=row.max_product_version,
    )


USER_LIMITS = ("named_users", "active_users")
_MAX_VERSION = re.compile(r"(\d+(\.\d+){0,2})?")


def _check_limits(value: Any) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """{named_users | active_users: positive int or null, only_count_active: bool}."""
    if not isinstance(value, dict) or set(value) - {*USER_LIMITS, "only_count_active"}:
        return {}, {"limits": ["Допустимы named_users, active_users, only_count_active."]}
    clean: dict[str, Any] = {}
    for key in USER_LIMITS:
        number = value.get(key)
        if number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            return {}, {"limits": ["Лимит пользователей — целое число не меньше 1."]}
        clean[key] = number
    only_active = value.get("only_count_active", False)
    if not isinstance(only_active, bool):
        return {}, {"limits": ["only_count_active — да или нет."]}
    if clean or only_active:
        clean["only_count_active"] = only_active
    return clean, {}


def _locked(license_id: UUID) -> License:
    row = (
        License.objects.select_for_update(of=("self",))
        .select_related("customer")
        .filter(id=license_id)
        .first()
    )
    if row is None:
        raise DomainError("not_found", "license not found")
    return row


def _reason(reason: str) -> str:
    text = reason.strip()
    if not text:
        raise _invalid({"reason": ["Укажите причину."]})
    return text


def _filtered(
    *,
    product_id: UUID | None = None,
    customer_id: UUID | None = None,
    status: str = "",
    expires_before: datetime | None = None,
    expires_after: datetime | None = None,
) -> Any:
    if status and status not in LicenseStatus.values:
        raise _invalid({"status": ["Недопустимое значение."]})
    rows = License.objects.select_related("customer").prefetch_related("keys")
    if product_id:
        rows = rows.filter(product_id=product_id)
    if customer_id:
        rows = rows.filter(customer_id=customer_id)
    if status:
        rows = rows.filter(status=status)
    if expires_before:
        rows = rows.filter(valid_until__lt=expires_before)
    if expires_after:
        rows = rows.filter(valid_until__gte=expires_after)
    return rows


def list_licenses(
    *,
    product_id: UUID | None = None,
    customer_id: UUID | None = None,
    status: str = "",
    expires_before: datetime | None = None,
    expires_after: datetime | None = None,
    ordering: str = "valid_until",
    page: int = 1,
    page_size: int = 20,
) -> LicensePage:
    if ordering not in ORDERINGS or not 1 <= page_size <= MAX_PAGE_SIZE or page < 1:
        raise _invalid({})
    rows = _filtered(
        product_id=product_id,
        customer_id=customer_id,
        status=status,
        expires_before=expires_before,
        expires_after=expires_after,
    ).order_by(ordering, "id")
    start = (page - 1) * page_size
    return LicensePage(rows.count(), [_data(r) for r in rows[start : start + page_size]])


def find_licenses(
    *, product_id: UUID | None = None, customer_id: UUID | None = None, limit: int = 10_000
) -> list[LicenseData]:
    """All licences of the filters, for statistics and its export (E10-01, E10-02)."""
    rows = _filtered(product_id=product_id, customer_id=customer_id).order_by(
        "customer__name", "id"
    )
    return [_data(r) for r in rows[:limit]]


def get_license(license_id: UUID, *, customer_id: UUID | None = None) -> LicenseData:
    """customer_id limits the lookup to one customer (a customer viewer, E07-08)."""
    rows = License.objects.select_related("customer").prefetch_related("keys").filter(id=license_id)
    if customer_id is not None:
        rows = rows.filter(customer_id=customer_id)
    row = rows.first()
    if row is None:
        raise DomainError("not_found", "license not found")
    return _data(row)


def _check_terms(values: dict[str, Any]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    if values.get("type") not in LicenseType.values:
        errors["type"] = ["Недопустимое значение."]
    limit = values.get("limit")
    if not isinstance(limit, int) or limit < 1:
        errors["limit"] = ["Количество мест — целое число больше нуля."]
    reserve = values.get("reserve_pct")
    if reserve is not None and (not isinstance(reserve, int) or not 0 <= reserve <= 100):
        errors["reserve_pct"] = ["Резерв — от 0 до 100 %."]
    if values.get("enforcement", "") not in ("", *Enforcement.values):
        errors["enforcement"] = ["Недопустимое значение."]
    valid_from, valid_until = values.get("valid_from"), values.get("valid_until")
    if valid_until is not None and valid_from is not None and valid_until < valid_from:
        errors["valid_until"] = ["Срок окончания раньше начала."]
    if values.get("type") == LicenseType.PERPETUAL and valid_until is not None:
        errors["valid_until"] = ["У бессрочной лицензии нет срока окончания."]
    return errors


def create_license(
    values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> LicenseData:
    """values: customer_id, product_id, edition_id?, metric_id, type, limit, valid_from, …"""
    errors = _check_terms(values)
    customer_id = values.get("customer_id")
    customer = Customer.objects.filter(id=customer_id).first() if customer_id else None
    if customer is None:
        errors["customer_id"] = ["Заказчик не найден."]
    elif customer.status == "archived":
        errors["customer_id"] = ["Заказчик в архиве."]
    if errors or customer is None:
        raise _invalid(errors)
    with transaction.atomic():
        row = License.objects.create(
            customer=customer,
            product_id=values["product_id"],
            edition_id=values.get("edition_id"),
            metric_id=values["metric_id"],
            type=values["type"],
            limit=values["limit"],
            reserve_pct=values.get("reserve_pct"),
            valid_from=values["valid_from"],
            valid_until=values.get("valid_until"),
            support_until=values.get("support_until"),
            policy_profile_code=values.get("policy_profile_code", ""),
            enforcement=values.get("enforcement", ""),
            created_at=now,
            updated_at=now,
        )
        record(
            actor,
            "license.created",
            "license",
            str(row.id),
            at=now,
            ip=ip,
            data={"limit": row.limit},
        )
    return get_license(row.id)


def _save(
    row: License, actor: str, action: str, now: datetime, ip: str | None, data: dict[str, Any]
) -> LicenseData:
    row.updated_at = now
    row.save()
    record(actor, action, "license", str(row.id), at=now, ip=ip, data=data)
    return get_license(row.id)


def renew_license(
    license_id: UUID,
    *,
    valid_until: datetime | None,
    support_until: datetime | None,
    limit: int | None,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> LicenseData:
    with transaction.atomic():
        row = _locked(license_id)
        if row.status == LicenseStatus.REVOKED:
            raise _invalid({"status": ["Отозванную лицензию нельзя продлить."]})
        new_limit = row.limit if limit is None else limit
        values: dict[str, Any] = {
            "type": row.type,
            "limit": new_limit,
            "valid_from": row.valid_from,
            "valid_until": valid_until,
        }
        errors = _check_terms(values)
        if errors:
            raise _invalid(errors)
        row.valid_until, row.support_until, row.limit = valid_until, support_until, new_limit
        row.rights_version += 1
        return _save(
            row,
            actor,
            "license.renewed",
            now,
            ip,
            {"valid_until": valid_until.isoformat() if valid_until else None, "limit": row.limit},
        )


def set_license_status(
    license_id: UUID, status: str, *, reason: str, actor: str, now: datetime, ip: str | None = None
) -> LicenseData:
    """suspended (приостановить), active (возобновить), revoked (отозвать — навсегда)."""
    text = (
        _reason(reason)
        if status in (LicenseStatus.REVOKED, LicenseStatus.SUSPENDED)
        else reason.strip()
    )
    with transaction.atomic():
        row = _locked(license_id)
        if row.status == LicenseStatus.REVOKED:
            raise _invalid({"status": ["Лицензия отозвана, состояние не меняется."]})
        if status not in LicenseStatus.values or status == row.status:
            raise _invalid({"status": ["Недопустимое значение."]})
        previous, row.status = row.status, status
        action = {
            "suspended": "license.suspended",
            "active": "license.resumed",
            "revoked": "license.revoked",
        }[status]
        return _save(row, actor, action, now, ip, {"from": previous, "reason": text})


def lift_block(
    license_id: UUID,
    *,
    until: datetime,
    reason: str,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> LicenseData:
    """Снять блок: monitor until the date (section 8.3 of document 1); rights_version + 1."""
    text = _reason(reason)
    if until <= now:
        raise _invalid({"until": ["Дата должна быть в будущем."]})
    with transaction.atomic():
        row = _locked(license_id)
        if row.status == LicenseStatus.REVOKED:
            raise _invalid({"status": ["С отозванной лицензии блок не снимается."]})
        row.monitor_until = until
        row.rights_version += 1
        return _save(
            row,
            actor,
            "license.block_lifted",
            now,
            ip,
            {"until": until.isoformat(), "reason": text},
        )


def update_settings(
    license_id: UUID, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> LicenseData:
    """E01-07: limit, reserve_pct, metric_id, enforcement (monitor / enforce / "" = profile);
    limits of users of a server product (E11-01)."""
    allowed = {"limit", "reserve_pct", "metric_id", "enforcement", "limits", "max_product_version"}
    changes = {key: value for key, value in values.items() if key in allowed}
    with transaction.atomic():
        row = _locked(license_id)
        candidate = {
            "type": row.type,
            "limit": changes.get("limit", row.limit),
            "reserve_pct": changes.get("reserve_pct", row.reserve_pct),
            "enforcement": changes.get("enforcement", row.enforcement),
        }
        errors = _check_terms(candidate)
        if "limits" in changes:
            changes["limits"], limit_errors = _check_limits(changes["limits"])
            errors |= limit_errors
        if "max_product_version" in changes:
            changes["max_product_version"] = str(changes["max_product_version"] or "").strip()
            if not _MAX_VERSION.fullmatch(changes["max_product_version"]):
                errors["max_product_version"] = [
                    "Версия — до трёх чисел через точку, например 3 или 3.2."
                ]
        if errors:
            raise _invalid(errors)
        for key, value in changes.items():
            setattr(row, key, value)
        return _save(
            row, actor, "license.settings_changed", now, ip, {k: str(v) for k, v in changes.items()}
        )


def transfer_license(
    license_id: UUID,
    customer_id: UUID,
    *,
    reason: str,
    document: str,
    allocated: Callable[[UUID], bool],
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> LicenseData:
    """E01-08: keys, activations and terms stay; refused while seats are with a local server.

    allocated(license_id) is asked under the row lock: quotas are given under the same lock."""
    text = _reason(reason)
    with transaction.atomic():
        row = _locked(license_id)
        if allocated(license_id):
            raise DomainError(
                "invalid_request",
                "seats are allocated to a local server",
                data={
                    "fields": {
                        "customer_id": ["Места выделены локальному серверу: сначала верните квоту."]
                    }
                },
            )
        target = Customer.objects.filter(id=customer_id).first()
        if target is None or target.id == row.customer_id:
            raise _invalid({"customer_id": ["Выберите другого заказчика."]})
        previous = row.customer_id
        row.customer = target
        return _save(
            row,
            actor,
            "license.transferred",
            now,
            ip,
            {
                "from": str(previous),
                "to": str(target.id),
                "reason": text,
                "document": document.strip(),
            },
        )


def _new_key(now: datetime) -> str:
    week, year = now.isocalendar()[1], now.year % 100
    return f"{week:02}{year:02}-" + "-".join(random_text(KEY_ALPHABET, 4) for _ in range(3))


def issue_key(license_id: UUID, *, actor: str, now: datetime, ip: str | None = None) -> IssuedKey:
    """A new key WWyy-XXXX-XXXX-XXXX (decision 6 of document 1); stored as hash and mask only."""
    with transaction.atomic():
        row = _locked(license_id)
        while True:
            key = normalize_key(_new_key(now))
            digest = key_hash(key)
            if not LicenseKey.objects.filter(key_hash=digest).exists():
                break
        mask = key_mask(key)
        LicenseKey.objects.create(license=row, key_hash=digest, key_mask=mask, format="v1")
        record(
            actor,
            "license.key_issued",
            "license",
            str(row.id),
            at=now,
            ip=ip,
            data={"key_mask": mask},
        )
    return IssuedKey(license_id=row.id, key=key, key_mask=mask)
