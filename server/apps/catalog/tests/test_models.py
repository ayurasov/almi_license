import pytest
from django.db import IntegrityError

from apps.catalog.models import Capability, PolicyProfile, Product
from infra.clock import FrozenClock

PARAMS = {"version": 1, "enforcement": "monitor", "notify_before_days": 30, "grace_days": 14,
          "expiry_action": "restrict", "check_interval_hours": 24}


@pytest.mark.django_db
def test_policy_profile_version_is_unique_per_code(clock: FrozenClock) -> None:
    PolicyProfile.objects.create(code="alteroffice-desktop.commercial", version=1, params=PARAMS,
                                 created_at=clock.now())
    PolicyProfile.objects.create(code="alteroffice-desktop.commercial", version=2, params=PARAMS,
                                 created_at=clock.now())
    with pytest.raises(IntegrityError):
        PolicyProfile.objects.create(code="alteroffice-desktop.commercial", version=2, params=PARAMS,
                                     created_at=clock.now())


@pytest.mark.django_db
def test_product_code_is_unique(product: Product, clock: FrozenClock) -> None:
    with pytest.raises(IntegrityError):
        Product.objects.create(code=product.code, name={"ru": "Дубль"}, default_metric=product.default_metric,
                               subject_type="device", created_at=clock.now())


@pytest.mark.django_db
def test_capability_code_is_unique_per_product(product: Product) -> None:
    Capability.objects.create(product=product, code="edit", name={"ru": "Редактирование"})
    with pytest.raises(IntegrityError):
        Capability.objects.create(product=product, code="edit", name={"ru": "Ещё раз"})
