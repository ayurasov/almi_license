"""manage.py local_status: JSON for scripts and --check lines for check.sh (E15-04)."""

import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_not_configured() -> None:
    out = StringIO()
    call_command("local_status", stdout=out)
    assert json.loads(out.getvalue())["configured"] is False
    out = StringIO()
    call_command("local_status", "--check", stdout=out)
    assert out.getvalue().startswith("warn  not registered")


def test_registered_package(clock: Any) -> None:
    from datetime import timedelta

    from apps.packages.models import LocalIdentity
    from infra.clock import use_clock

    LocalIdentity.objects.create(
        server_id="srv_01JABF8Q4W2N8C1R7ZB0Y5K6M3",
        exchange="files",
        public_key="k",
        package_seq=3,
        package_issued_at=clock.now(),
        package_valid_until=clock.now() + timedelta(days=10),
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    out = StringIO()
    with use_clock(clock):
        call_command("local_status", "--check", stdout=out)
    assert "ok    package 3" in out.getvalue()
    assert "expires in less than 30 days" in out.getvalue()
    clock.advance(timedelta(days=11))
    with use_clock(clock), pytest.raises(CommandError):
        call_command("local_status", "--check", stdout=StringIO())
