"""manage.py verify_audit: recompute the hash chain of the audit log (E10-03).

Exit status 0 with the number of events, or 1 with the first broken seq.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.audit.domain import verify_chain


class Command(BaseCommand):
    help = "Check the hash chain of the audit log."

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            count = verify_chain()
        except ValueError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(f"audit chain is intact: {count} events")
