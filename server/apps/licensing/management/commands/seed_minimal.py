"""manage.py seed_minimal --trial --out FILE: the seed-minimal data set (section 4 of document 7).

Three customers and ten licences of every product, type and state worth a manual test: a trial,
a perpetual one, terms ending soon and already over, monitor mode, user limits of the web product,
the AlterOS workstation. Made by the licensing domain with audit, as an operator would. The full
keys go to --out only (0600, AGENTS.md rule 9); the output names their masks. "--out -" writes
the keys as JSON to stdout and the rest to stderr, for a container: "... --out - > keys.json".
For dev and trial servers: --trial is required, and a second run changes nothing.
"""

import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.domain import list_products
from apps.licensing.domain import (
    create_customer,
    create_license,
    issue_key,
    key_mask,
    list_customers,
    update_settings,
)
from infra.clock import current_clock

ACTOR = "system:seed-minimal"
PREFIX = "Тестовый заказчик"
CUSTOMERS = [f"{PREFIX} 1 (ООО «Альфа»)", f"{PREFIX} 2 (АО «Бета»)", f"{PREFIX} 3 (ГБУ «Гамма»)"]
DESKTOP, WEB, OS = "alteroffice-desktop", "alteroffice-web", "alteros"


@dataclass(frozen=True)
class Seed:
    """A licence of the set; its terms are days from now, None is no end."""

    customer: int
    product: str
    edition: str
    type: str
    seats: int
    note: str
    start: int = -30
    end: int | None = 365
    support: int | None = 365
    enforcement: str = "enforce"
    limits: dict[str, Any] = field(default_factory=dict)


USERS_10 = {"named_users": 10, "only_count_active": False}
ACTIVE_5 = {"active_users": 5, "only_count_active": True}
LICENSES = [
    Seed(0, DESKTOP, "standard", "subscription", 3, "подписка, 3 места"),
    Seed(0, DESKTOP, "professional", "perpetual", 2, "бессрочная", end=None, enforcement=""),
    Seed(0, DESKTOP, "standard", "trial", 1, "пробная, 14 дней", start=-1, end=14, support=None),
    Seed(1, DESKTOP, "standard", "subscription", 5, "срок через 10 дней", start=-355, end=10),
    Seed(1, DESKTOP, "standard", "subscription", 2, "срок прошёл", start=-370, end=-5, support=-5),
    Seed(2, DESKTOP, "professional", "nfr", 1, "NFR, наблюдение", end=180, enforcement="monitor"),
    Seed(0, WEB, "enterprise", "subscription", 1, "Nextcloud: 10 пользователей", limits=USERS_10),
    Seed(1, WEB, "enterprise", "subscription", 1, "Nextcloud: 5 активных", end=20, limits=ACTIVE_5),
    Seed(2, OS, "workstation", "subscription", 2, "АльтерОС: 2 станции"),
    Seed(2, OS, "workstation", "free", 1, "АльтерОС: бесплатная", end=None, support=None),
]


def synthetic_inn(n: int) -> str:
    """A ten-digit INN of a legal entity with a valid check digit, not of a real organisation."""
    body = f"770999{n:03d}"
    total = sum(int(d) * w for d, w in zip(body, [2, 4, 10, 3, 5, 9, 4, 6, 8], strict=True))
    return body + str(total % 11 % 10)


class Command(BaseCommand):
    help = "Create the seed-minimal data set for manual tests (dev and trial servers)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--trial", action="store_true", help="confirm: not a production server")
        parser.add_argument(
            "--out", required=True, help="file for the full keys (0600), - for stdout"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        to_stdout = options["out"] == "-"
        say = self.stderr.write if to_stdout else self.stdout.write
        if not options["trial"]:
            raise CommandError("seed_minimal is for dev and trial servers: pass --trial")
        if list_customers(name=PREFIX).count:
            say("seed-minimal is already loaded: nothing changed")
            return
        now = current_clock().now()
        day = timedelta(days=1)
        products = {p["code"]: p for p in list_products()}
        customers = [
            create_customer({"name": name, "inn": synthetic_inn(n)}, actor=ACTOR, now=now).id
            for n, name in enumerate(CUSTOMERS, 1)
        ]
        rows = []
        for seed in LICENSES:
            product = products[seed.product]
            editions = {e["code"]: e["id"] for e in product["editions"]}
            lic = create_license(
                {
                    "customer_id": customers[seed.customer],
                    "product_id": product["id"],
                    "edition_id": editions[seed.edition],
                    "metric_id": product["default_metric_id"],
                    "type": seed.type,
                    "limit": seed.seats,
                    "valid_from": now + seed.start * day,
                    "valid_until": None if seed.end is None else now + seed.end * day,
                    "support_until": None if seed.support is None else now + seed.support * day,
                    "enforcement": seed.enforcement,
                },
                actor=ACTOR,
                now=now,
            )
            if seed.limits:
                update_settings(lic.id, {"limits": seed.limits}, actor=ACTOR, now=now)
            key = issue_key(lic.id, actor=ACTOR, now=now).key
            rows.append({"product": seed.product, "type": seed.type, "note": seed.note, "key": key})
            say(f"{seed.product:20} {seed.type:12} {key_mask(key)}  {seed.note}")
        document = json.dumps(rows, ensure_ascii=False, indent=2)
        if to_stdout:
            self.stdout.write(document)
            say(f"{len(rows)} licences")
            return
        out = Path(options["out"])
        out.write_text(document, encoding="utf-8")
        out.chmod(0o600)
        say(f"{len(rows)} licences; the keys are in {out}")
