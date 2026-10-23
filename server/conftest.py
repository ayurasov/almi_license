"""Shared fixtures. This file is outside the apps package, so it may build objects of several
modules for tests; module code itself crosses boundaries only through <module>.domain."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from infra.clock import FrozenClock

if TYPE_CHECKING:
    from apps.catalog.models import Product
    from apps.licensing.models import License

NOW = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def product(db: None, clock: FrozenClock) -> "Product":
    from apps.catalog.models import Metric, Product

    metric = Metric.objects.create(code="device", name={"ru": "Устройство"})
    return Product.objects.create(
        code="alteroffice-desktop",
        name={"ru": "АльтерОфис Desktop"},
        default_metric=metric,
        subject_type="device",
        created_at=clock.now(),
    )


@pytest.fixture
def license_(product: "Product", clock: FrozenClock) -> "License":
    from apps.licensing.models import Customer, License

    customer = Customer.objects.create(
        name="ООО «Пример»", inn="7701234567", created_at=clock.now()
    )
    return License.objects.create(
        customer=customer,
        product=product,
        metric=product.default_metric,
        type="subscription",
        limit=10,
        valid_from=clock.now(),
        status="active",
        created_at=clock.now(),
        updated_at=clock.now(),
    )
