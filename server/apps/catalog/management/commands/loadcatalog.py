"""manage.py loadcatalog [file] — the initial catalog (default: fixtures/catalog-v1.json)."""

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.catalog.domain.loader import load_catalog
from infra.clock import current_clock

DEFAULT = Path(__file__).resolve().parents[2] / "fixtures" / "catalog-v1.json"


class Command(BaseCommand):
    help = "Load products, editions, capabilities, metrics and policy profiles (E01-02)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("file", nargs="?", default=str(DEFAULT))

    def handle(self, *args: Any, **options: Any) -> None:
        document = json.loads(Path(options["file"]).read_text(encoding="utf-8"))
        counts = load_catalog(document, now=current_clock().now())
        self.stdout.write(", ".join(f"{name}: {value}" for name, value in counts.items()))
