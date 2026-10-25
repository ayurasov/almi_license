"""Article mapping of the LK (E06-02): field AA -> product, edition and metric of the catalog."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.audit.domain import record
from apps.catalog.domain import list_metrics, product_details
from apps.licensing.models import ArticleMapping
from infra.errors import DomainError

AA = re.compile(r"[0-9A-Za-z]{1,8}")


@dataclass(frozen=True)
class MappingData:
    aa: str
    product_id: UUID
    edition_id: UUID | None
    metric_id: UUID


def _data(row: ArticleMapping) -> MappingData:
    return MappingData(row.aa, row.product_id, row.edition_id, row.metric_id)


def list_mappings() -> list[MappingData]:
    return [_data(row) for row in ArticleMapping.objects.order_by("aa")]


def save_mapping(
    aa: str, values: dict[str, Any], *, actor: str, now: datetime, ip: str | None = None
) -> MappingData:
    """Creates or replaces the mapping; the next preview of the file uses it."""
    errors: dict[str, list[str]] = {}
    if not AA.fullmatch(aa):
        errors["aa"] = ["Поле AA: 1–8 латинских букв или цифр."]
    product = product_details(values["product_id"])
    editions = {e["id"] for e in product["editions"]}
    if values.get("edition_id") is not None and values["edition_id"] not in editions:
        errors["edition_id"] = ["Редакция не относится к продукту."]
    if values["metric_id"] not in {m["id"] for m in list_metrics()}:
        errors["metric_id"] = ["Метрика не найдена."]
    if errors:
        raise DomainError("invalid_request", "mapping is invalid", data={"fields": errors})
    with transaction.atomic():
        row, _ = ArticleMapping.objects.update_or_create(
            aa=aa,
            defaults={
                "product_id": values["product_id"],
                "edition_id": values.get("edition_id"),
                "metric_id": values["metric_id"],
            },
        )
        record(
            actor,
            "import.mapping_saved",
            "article",
            aa,
            at=now,
            ip=ip,
            data={"product": product["code"]},
        )
    return _data(row)
