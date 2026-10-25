"""manage.py grant_app_role ROLE [--password-file FILE]: the application role (question 38).

Run by the owner of the tables right after the migrations (deploy/entrypoint.sh, migrate). The
API and the worker connect as ROLE: it reads and writes the tables but owns none of them, so it
cannot ALTER, TRUNCATE or disable the append-only trigger of the audit journal; on the journal it
has SELECT and INSERT only. With --password-file the role is created (or its password set); the
password is read from the file and never printed.
"""

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import connection
from psycopg import sql

from apps.audit.models import AuditEvent

AUDIT_TABLE = AuditEvent._meta.db_table


def grant_statements(role: str) -> list[sql.Composed]:
    name = sql.Identifier(role)
    audit = sql.Identifier(AUDIT_TABLE)
    return [
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(connection.settings_dict["NAME"]), name
        ),
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(name),
        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(
            name
        ),
        sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON {} FROM {}").format(audit, name),
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(name),
    ]


class Command(BaseCommand):
    help = "Grant the application role DML rights; the audit journal is append-only for it."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("role")
        parser.add_argument("--password-file", type=Path, default=None)

    def handle(self, *args: Any, **options: Any) -> None:
        role: str = options["role"]
        password_file: Path | None = options["password_file"]
        with connection.cursor() as cursor:
            if password_file is not None:
                password = password_file.read_text(encoding="utf-8").strip()
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
                verb = "ALTER" if cursor.fetchone() else "CREATE"
                cursor.execute(
                    sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}")
                    .format(sql.Identifier(role), sql.Literal(password))
                    .as_string(cursor.connection)
                )
            for statement in grant_statements(role):
                cursor.execute(statement.as_string(cursor.connection))
        self.stdout.write(f"rights of {role} granted")
