"""manage.py create_account --username <name> --role operator|admin|customer_viewer

The password is read from the environment variable CONSOLE_PASSWORD or asked without echo;
it is never an argument (it would stay in the shell history and the process list).
"""

import getpass
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.iam.domain import create_account
from infra.clock import current_clock


class Command(BaseCommand):
    help = "Create a console account (E07-02)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--username", required=True)
        parser.add_argument(
            "--role", required=True, choices=["operator", "admin", "customer_viewer"]
        )

    def handle(self, *args: Any, **options: Any) -> None:
        password = os.environ.get("CONSOLE_PASSWORD") or getpass.getpass("Password: ")
        if len(password) < 12:
            raise CommandError("the password must be at least 12 characters")
        create_account(options["username"], password, options["role"], now=current_clock().now())
        self.stdout.write(f"account {options['username']} ({options['role']}) created")
