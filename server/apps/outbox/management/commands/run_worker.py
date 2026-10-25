"""manage.py run_worker [--once]: the task worker (E12-01, prompt I4-03).

Every pass queues the due slots of the schedule (one worker at a time, advisory lock) and runs
due tasks in batches; when nothing is due it sleeps --idle seconds. Several workers can run.
"""

import threading
from datetime import datetime, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.outbox.domain import run_due, schedule_due
from infra.clock import current_clock

IDLE_SECONDS = 5
SCHEDULE = timedelta(minutes=1)


class Command(BaseCommand):
    help = "Run queued tasks and the schedule of periodic tasks."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="one pass, then exit")
        parser.add_argument("--idle", type=float, default=IDLE_SECONDS, help="sleep when idle")

    def handle(self, *args: Any, **options: Any) -> None:
        stop = threading.Event()
        next_schedule: datetime | None = None
        while True:
            now = current_clock().now()
            if next_schedule is None or now >= next_schedule:
                schedule_due(now=now)
                next_schedule = now + SCHEDULE
            ran = 0
            while batch := run_due(now=current_clock().now()):
                ran += batch
            if ran:
                self.stdout.write(f"{ran} tasks run")
            if options["once"] or stop.wait(options["idle"]):
                return
