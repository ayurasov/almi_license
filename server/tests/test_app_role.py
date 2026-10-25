"""Question 38: the application role reads and writes, but the audit journal stays append-only."""

import secrets
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from django.core.management import call_command
from django.db import connection
from psycopg import sql

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def app_role(tmp_path: Path) -> Iterator[tuple[str, str]]:
    role = f"almi_app_test_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(18)
    (tmp_path / "password").write_text(password + "\n", encoding="utf-8")
    call_command("grant_app_role", role, "--password-file", str(tmp_path / "password"))
    yield role, password
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("DROP OWNED BY {0}; DROP ROLE {0}")
            .format(sql.Identifier(role))
            .as_string(cursor.connection)
        )


def connect(role: str, password: str) -> psycopg.Connection:
    params = connection.settings_dict
    return psycopg.connect(
        host=params["HOST"] or "localhost",
        port=params["PORT"] or 5432,
        dbname=params["NAME"],
        user=role,
        password=password,
        autocommit=True,
    )


def test_app_role_rights(app_role: tuple[str, str]) -> None:
    from apps.audit.domain import record
    from apps.audit.models import AuditEvent
    from infra.clock import SystemClock

    record("system", "test.event", "test", "1", at=SystemClock().now())
    table = AuditEvent._meta.db_table
    with connect(*app_role) as app:
        assert app.execute(f"SELECT count(*) FROM {table}").fetchone() == (1,)  # noqa: S608
        app.execute("SELECT count(*) FROM licensing_customer")
        for statement in (
            f"UPDATE {table} SET action = 'x'",  # noqa: S608
            f"DELETE FROM {table}",  # noqa: S608
            f"TRUNCATE {table}",
            f"ALTER TABLE {table} DISABLE TRIGGER ALL",
            "CREATE TABLE intruder (id int)",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(statement)
    assert AuditEvent.objects.count() == 1
