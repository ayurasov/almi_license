"""manage.py sync_package [--every MINUTES]: a local server asks the central server for a newer
package (GET /api/sync/v1/servers/{id}/package?since_seq, E09-03). Without --every it runs once
(cron, systemd timer); with it, it repeats in the foreground (the sync service of docker compose).
"""

import threading
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.packages.domain import sync_package
from infra.clock import current_clock
from infra.errors import DomainError


class Command(BaseCommand):
    help = "Fetch a newer package from the central server (local server, online exchange)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--every", type=int, default=0, help="repeat every N minutes")

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.DEPLOYMENT_MODE != "local":
            raise CommandError("sync_package runs on a local server (DEPLOYMENT_MODE=local)")
        stop = threading.Event()
        while True:
            self._once()
            if options["every"] <= 0 or stop.wait(options["every"] * 60):
                return

    def _once(self) -> None:
        try:
            status = sync_package(now=current_clock().now())
        except DomainError as error:
            # The previous package stays; the next run tries again.
            self.stderr.write(f"package not updated: {error.detail}")
            return
        if status is None:
            self.stdout.write("no newer package")
        else:
            self.stdout.write(f"package {status.package_seq} applied")
