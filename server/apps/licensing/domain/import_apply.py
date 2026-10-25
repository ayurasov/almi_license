"""Confirmation of an LK import (E06-03): customers, licenses and keys from a preview.

Idempotent by key: a key already in the database updates its license (terms from the export)
or is skipped when nothing changed; a key of another customer, product or edition is an error.
Each row is checked again against the database at confirmation time, since the preview may be
up to 24 hours old. One transaction for the whole session: a failure leaves nothing applied.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.audit.domain import record
from apps.licensing.models import (
    ArticleMapping,
    Customer,
    CustomerStatus,
    ExternalRef,
    ImportSession,
    ImportSessionStatus,
    KeyFormat,
    License,
    LicenseKey,
    LicenseStatus,
)
from infra.errors import DomainError


@dataclass(frozen=True)
class ImportReport:
    session_id: UUID
    created: int
    updated: int
    skipped: int
    errors: list[dict[str, Any]] = field(default_factory=list)
    customers_created: int = 0


def _moment(value: str | None) -> datetime | None:
    return None if value is None else parse_datetime(value)


def _customer(
    fields: dict[str, Any], actor: str, now: datetime, ip: str | None
) -> tuple[Customer, bool]:
    row = Customer.objects.filter(inn=fields["inn"]).first()
    if row is not None:
        return row, False
    name = fields.get("customer") or f"ИНН {fields['inn']}"
    row = Customer.objects.create(name=name, inn=fields["inn"], created_at=now)
    record(
        actor,
        "customer.created",
        "customer",
        str(row.id),
        at=now,
        ip=ip,
        data={"inn": row.inn, "source": "lk_import"},
    )
    return row, True


def _mapping_ids(fields: dict[str, Any]) -> tuple[UUID, UUID | None, UUID] | None:
    mapping = ArticleMapping.objects.filter(aa=fields.get("aa", "")).first()
    return None if mapping is None else (mapping.product_id, mapping.edition_id, mapping.metric_id)


def _apply_row(
    item: dict[str, Any], actor: str, now: datetime, ip: str | None
) -> tuple[str, str | None, bool]:
    """Outcome (created | updated | skipped | error), the reason of an error, customer created."""
    fields = item["fields"]
    ids = _mapping_ids(fields)
    if ids is None:
        return "error", f"Артикул не сопоставлен: {fields.get('aa', '')}", False
    product_id, edition_id, metric_id = ids
    valid_from, valid_until = _moment(fields["valid_from"]), _moment(fields["valid_until"])
    if valid_from is None:  # a row without errors always has the start of its term
        return "error", "Неверная дата выдачи", False
    key = LicenseKey.objects.filter(key_hash=item["key_hash"]).first()
    if key is None:
        customer, customer_created = _customer(fields, actor, now, ip)
        if customer.status == CustomerStatus.ARCHIVED:
            return "error", "Заказчик в архиве", customer_created
        license_ = License.objects.create(
            customer=customer,
            product_id=product_id,
            edition_id=edition_id,
            metric_id=metric_id,
            type=fields["type"],
            limit=fields["limit"],
            valid_from=valid_from,
            valid_until=valid_until,
            support_until=valid_until,
            created_at=now,
            updated_at=now,
        )
        LicenseKey.objects.create(
            license=license_,
            key_hash=item["key_hash"],
            key_mask=fields["key_mask"],
            format=KeyFormat.LEGACY,
            article=fields["article"],
        )
        if fields.get("serial"):
            ExternalRef.objects.get_or_create(
                system="lk", value=fields["serial"], defaults={"license": license_}
            )
        record(
            actor,
            "license.imported",
            "license",
            str(license_.id),
            at=now,
            ip=ip,
            data={"key_mask": fields["key_mask"], "limit": license_.limit, "row": item["row"]},
        )
        return "created", None, customer_created

    license_ = (
        License.objects.select_for_update(of=("self",))
        .select_related("customer")
        .get(id=key.license_id)
    )
    if license_.customer.inn != fields["inn"]:
        return "error", "Ключ принадлежит другому заказчику", False
    if license_.product_id != product_id or license_.edition_id != edition_id:
        return "error", "Ключ выдан на другой продукт или редакцию", False
    if license_.status == LicenseStatus.REVOKED:
        return "error", "Лицензия отозвана", False
    terms = {
        "type": fields["type"],
        "limit": fields["limit"],
        "valid_from": valid_from,
        "valid_until": valid_until,
    }
    if all(getattr(license_, name) == value for name, value in terms.items()):
        return "skipped", None, False
    previous = {
        "limit": license_.limit,
        "valid_until": license_.valid_until.isoformat() if license_.valid_until else None,
    }
    for name, value in terms.items():
        setattr(license_, name, value)
    license_.support_until = valid_until
    license_.rights_version += 1
    license_.updated_at = now
    license_.save()
    record(
        actor,
        "license.import_updated",
        "license",
        str(license_.id),
        at=now,
        ip=ip,
        data={
            "from": previous,
            "limit": license_.limit,
            "valid_until": fields["valid_until"],
            "row": item["row"],
        },
    )
    return "updated", None, False


def apply_import(
    session_id: UUID, *, actor: str, now: datetime, ip: str | None = None
) -> ImportReport:
    with transaction.atomic():
        session = ImportSession.objects.select_for_update().filter(id=session_id).first()
        if session is None:
            raise DomainError("not_found", "import session not found")
        if session.status != ImportSessionStatus.DRAFT:
            raise DomainError(
                "invalid_request",
                "import already applied",
                data={"fields": {"session_id": ["Импорт уже подтверждён."]}},
            )
        if now >= session.expires_at:
            session.status = ImportSessionStatus.EXPIRED
            session.save(update_fields=["status"])
            outcome: ImportReport | DomainError = DomainError(
                "invalid_request",
                "import session expired",
                data={"fields": {"session_id": ["Предпросмотр устарел: загрузите файл заново."]}},
            )
        else:
            counts = {"created": 0, "updated": 0, "skipped": 0}
            errors: list[dict[str, Any]] = []
            customers = 0
            for item in session.rows:
                if item["status"] == "error":
                    errors.append({"row": item["row"], "errors": item["errors"]})
                    continue
                result, reason, customer_created = _apply_row(item, actor, now, ip)
                customers += int(customer_created)
                if result == "error":
                    errors.append({"row": item["row"], "errors": [reason]})
                else:
                    counts[result] += 1
            outcome = ImportReport(session.id, **counts, errors=errors, customers_created=customers)
            session.status = ImportSessionStatus.APPLIED
            session.summary = {
                **session.summary,
                "report": {**counts, "errors": len(errors), "customers_created": customers},
            }
            session.save(update_fields=["status", "summary"])
            record(
                actor,
                "import.applied",
                "import",
                str(session.id),
                at=now,
                ip=ip,
                data={"filename": session.filename, **counts, "errors": len(errors)},
            )
    if isinstance(outcome, DomainError):
        raise outcome
    return outcome
