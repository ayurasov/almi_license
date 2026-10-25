"""manage.py local_status [--check]: the state of this local server (check.sh, E15-04)."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.packages.domain import local_status
from infra.clock import current_clock


def _plain(value: Any) -> Any:
    """Times as RFC 3339, UUIDs as text, the rest as it is."""
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


class Command(BaseCommand):
    help = "Print the state of the local server (registration, package, reports) as JSON."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--check", action="store_true", help="lines for check.sh; exit 1")

    def handle(self, *args: Any, **options: Any) -> None:
        status = local_status(current_clock().now())
        if not options["check"]:
            data = asdict(status)
            self.stdout.write(json.dumps({key: _plain(value) for key, value in data.items()}))
            return
        if not status.registered:
            self.stdout.write("warn  not registered yet: run the first-run wizard in the console")
            return
        until = _plain(status.package_valid_until)
        self.stdout.write(f"ok    package {status.package_seq}, valid until {until}")
        if status.package_expires_soon:
            self.stdout.write("warn  the package expires in less than 30 days: get a new one")
        self.stdout.write(
            f"ok    usage reports: sent {status.report_seq}, acknowledged {status.receipt_seq}"
        )
        if (
            status.package_valid_until is not None
            and status.package_valid_until <= current_clock().now()
        ):
            raise CommandError("the package has expired")
