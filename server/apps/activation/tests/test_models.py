import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.activation.models import Activation, Lease
from infra.clock import FrozenClock
from tests.db import indexed_column_sets

INSTANCE = uuid.UUID("8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c11")


def make(license_, clock: FrozenClock, external_id: str, status: str = "active") -> Activation:  # noqa: ANN001
    return Activation.objects.create(
        external_id=external_id, license=license_, instance_id=INSTANCE, subject_type="device",
        fp_components={"scheme": "fp-v1", "components": {"disk": "test-fp-disk"}}, device_pubkey="test-pub",
        status=status, product_version="3.2.0", os={"family": "linux"}, activated_at=clock.now(),
        last_seen_at=clock.now(), created_at=clock.now(),
    )


@pytest.mark.django_db
def test_one_active_activation_per_license_and_instance(license_, clock: FrozenClock) -> None:  # noqa: ANN001
    make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3")
    with pytest.raises(IntegrityError), transaction.atomic():
        make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M4")


@pytest.mark.django_db
def test_released_activations_do_not_block_a_new_one(license_, clock: FrozenClock) -> None:  # noqa: ANN001
    make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", status="released")
    make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M4", status="released_auto")
    make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M5")


@pytest.mark.django_db
def test_external_id_is_unique_and_formatted(license_, clock: FrozenClock) -> None:  # noqa: ANN001
    make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", status="released")
    with pytest.raises(IntegrityError), transaction.atomic():
        make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", status="released")
    with pytest.raises(IntegrityError), transaction.atomic():
        make(license_, clock, "act_not-a-ulid", status="released")


@pytest.mark.django_db
def test_unknown_status_is_rejected(license_, clock: FrozenClock) -> None:  # noqa: ANN001
    with pytest.raises(IntegrityError):
        make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", status="deleted")


@pytest.mark.django_db
def test_one_lease_per_activation(license_, clock: FrozenClock) -> None:  # noqa: ANN001
    activation = make(license_, clock, "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3")
    Lease.objects.create(activation=activation, seq=1, issued_at=clock.now(), jws_hash="0" * 64)
    with pytest.raises(IntegrityError):
        Lease.objects.create(activation=activation, seq=2, issued_at=clock.now(), jws_hash="1" * 64)


@pytest.mark.django_db
def test_indexes() -> None:
    assert ("status", "last_seen_at") in indexed_column_sets(Activation)
