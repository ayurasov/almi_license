import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.packages.models import Allocation, LocalServer, Package, UsageReport
from infra.clock import FrozenClock

LICENSE_ID = uuid.UUID("6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60")


@pytest.fixture
def server(db: None, clock: FrozenClock) -> LocalServer:
    return LocalServer.objects.create(
        external_id="srv_01JAB3K9M2N4P6Q8R0S2T4V6W8",
        customer_id=uuid.uuid4(),
        name="Контур заказчика",
        status="active",
        created_at=clock.now(),
    )


def test_server_external_id_format(server: LocalServer, clock: FrozenClock) -> None:
    with pytest.raises(IntegrityError):
        LocalServer.objects.create(
            external_id="server-1",
            customer_id=uuid.uuid4(),
            name="x",
            status="active",
            created_at=clock.now(),
        )


def test_allocation_unique_per_server_and_license(server: LocalServer) -> None:
    Allocation.objects.create(local_server=server, license_id=LICENSE_ID, seats=10)
    with pytest.raises(IntegrityError):
        Allocation.objects.create(local_server=server, license_id=LICENSE_ID, seats=5)


def test_package_and_report_seq_unique_per_server(server: LocalServer, clock: FrozenClock) -> None:
    Package.objects.create(
        local_server=server, seq=1, issued_at=clock.now(), valid_until=clock.now(), hash="0" * 64
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Package.objects.create(
            local_server=server,
            seq=1,
            issued_at=clock.now(),
            valid_until=clock.now(),
            hash="1" * 64,
        )
    UsageReport.objects.create(
        local_server=server,
        seq=1,
        period_from=clock.now(),
        period_to=clock.now(),
        data={},
        received_at=clock.now(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        UsageReport.objects.create(
            local_server=server,
            seq=1,
            period_from=clock.now(),
            period_to=clock.now(),
            data={},
            received_at=clock.now(),
        )
