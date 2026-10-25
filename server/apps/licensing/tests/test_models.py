import pytest
from django.db import IntegrityError

from apps.licensing.models import Customer, License, LicenseKey
from infra.clock import FrozenClock
from tests.db import indexed_column_sets

KEY_HASH = "0" * 64


@pytest.mark.django_db
def test_key_hash_is_unique(license_: License) -> None:
    LicenseKey.objects.create(
        license=license_, key_hash=KEY_HASH, key_mask="AB26-****-****-0001", format="v1"
    )
    with pytest.raises(IntegrityError):
        LicenseKey.objects.create(
            license=license_, key_hash=KEY_HASH, key_mask="AB26-****-****-0002", format="v1"
        )


@pytest.mark.django_db
def test_customer_inn_is_unique(license_: License, clock: FrozenClock) -> None:
    with pytest.raises(IntegrityError):
        Customer.objects.create(
            name="Другое имя", inn=license_.customer.inn, created_at=clock.now()
        )


@pytest.mark.django_db
def test_customers_without_inn_do_not_clash(clock: FrozenClock) -> None:
    Customer.objects.create(name="Иностранный заказчик 1", inn="", created_at=clock.now())
    Customer.objects.create(name="Иностранный заказчик 2", inn="", created_at=clock.now())


@pytest.mark.django_db
def test_key_mask_must_hide_the_middle_groups(license_: License) -> None:
    with pytest.raises(IntegrityError):
        LicenseKey.objects.create(
            license=license_, key_hash="1" * 64, key_mask="AB26-TEST-0000-0001", format="v1"
        )


@pytest.mark.django_db
def test_indexes() -> None:
    assert ("status", "valid_until") in indexed_column_sets(License)
    assert ("key_hash",) in indexed_column_sets(LicenseKey)
