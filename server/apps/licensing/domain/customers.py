"""Customers (E01-04): list with filters, create, update; every change goes to the audit log."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.domain import record
from apps.licensing.domain.inn import inn_is_valid
from apps.licensing.models import Customer, CustomerStatus
from infra.errors import DomainError

ORDERINGS = frozenset({"name", "-name", "inn", "-inn", "created_at", "-created_at"})
MAX_PAGE_SIZE = 100
FIELDS = ("name", "inn", "external_id", "status")


@dataclass(frozen=True)
class CustomerData:
    id: UUID
    name: str
    inn: str
    external_id: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class CustomerPage:
    count: int
    results: list[CustomerData]


def _data(row: Customer) -> CustomerData:
    return CustomerData(row.id, row.name, row.inn, row.external_id, row.status, row.created_at)


def _invalid(fields: dict[str, list[str]]) -> DomainError:
    return DomainError("invalid_request", "customer fields are invalid", data={"fields": fields})


def list_customers(
    *,
    name: str = "",
    inn: str = "",
    status: str = "",
    ordering: str = "name",
    page: int = 1,
    page_size: int = 20,
) -> CustomerPage:
    if ordering not in ORDERINGS or not 1 <= page_size <= MAX_PAGE_SIZE or page < 1:
        raise _invalid({})
    if status and status not in CustomerStatus.values:
        raise _invalid({"status": ["Недопустимое значение."]})
    rows = Customer.objects.all()
    if name:
        rows = rows.filter(name__icontains=name)
    if inn:
        rows = rows.filter(inn__startswith=inn)
    if status:
        rows = rows.filter(status=status)
    rows = rows.order_by(ordering, "id")
    start = (page - 1) * page_size
    return CustomerPage(rows.count(), [_data(r) for r in rows[start : start + page_size]])


def get_customer(customer_id: UUID) -> CustomerData:
    row = Customer.objects.filter(id=customer_id).first()
    if row is None:
        raise DomainError("invalid_request", "customer not found")
    return _data(row)


def _validated(values: dict[str, Any], current: Customer | None) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    clean = {key: values[key] for key in FIELDS if key in values}
    name = str(clean.get("name", current.name if current else "")).strip()
    if not name:
        errors["name"] = ["Укажите наименование."]
    clean["name"] = name
    inn = str(clean.get("inn", current.inn if current else "")).strip()
    if inn and not inn_is_valid(inn):
        errors["inn"] = ["Неверный ИНН: 10 или 12 цифр с верной контрольной суммой."]
    clean["inn"] = inn
    external_id = str(clean.get("external_id", current.external_id if current else "")).strip()
    clean["external_id"] = external_id
    status = clean.get("status", current.status if current else CustomerStatus.ACTIVE)
    if status not in CustomerStatus.values:
        errors["status"] = ["Недопустимое значение."]
    clean["status"] = status

    others = Customer.objects.exclude(id=current.id) if current else Customer.objects.all()
    if inn and "inn" not in errors and others.filter(inn=inn).exists():
        errors["inn"] = ["Заказчик с таким ИНН уже есть."]
    if external_id and others.filter(external_id=external_id).exists():
        errors["external_id"] = ["Заказчик с таким идентификатором ЛК уже есть."]
    if errors:
        raise _invalid(errors)
    return clean


def create_customer(
    values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> CustomerData:
    with transaction.atomic():
        clean = _validated(values, None)
        row = Customer.objects.create(**clean, created_at=now)
        record(actor, "customer.created", "customer", str(row.id), at=now, ip=ip, data=clean)
    return _data(row)


def update_customer(
    customer_id: UUID, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> CustomerData:
    with transaction.atomic():
        row = Customer.objects.select_for_update().filter(id=customer_id).first()
        if row is None:
            raise DomainError("invalid_request", "customer not found")
        clean = _validated(values, row)
        changed = {key: value for key, value in clean.items() if getattr(row, key) != value}
        for key, value in changed.items():
            setattr(row, key, value)
        row.save()
        if changed:
            record(actor, "customer.updated", "customer", str(row.id), at=now, ip=ip, data=changed)
    return _data(row)
