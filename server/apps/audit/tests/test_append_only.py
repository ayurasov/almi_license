"""The audit log cannot be changed in place (E10-03): the database refuses UPDATE and DELETE,
and verify_audit finds an edited event."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection, transaction

from apps.audit.domain import record
from apps.audit.models import AuditEvent
from infra.clock import FrozenClock

pytestmark = pytest.mark.django_db


def test_update_and_delete_are_refused(clock: FrozenClock) -> None:
    record("user:op", "license.created", "license", "l1", at=clock.now())
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.update(actor="someone else")
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get().actor == "user:op"


def test_verify_audit_command(clock: FrozenClock) -> None:
    for n in range(3):
        record("user:op", "license.created", "license", f"l{n}", at=clock.now())
    out = StringIO()
    call_command("verify_audit", stdout=out)
    assert "3 events" in out.getvalue()

    # An edit behind the trigger's back (e.g. by a superuser who disabled it) breaks the chain.
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_auditevent_append_only")
        cursor.execute("UPDATE audit_auditevent SET actor = 'forged' WHERE seq = 2")
        cursor.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_auditevent_append_only")
    with pytest.raises(CommandError, match="seq 2"):
        call_command("verify_audit")
