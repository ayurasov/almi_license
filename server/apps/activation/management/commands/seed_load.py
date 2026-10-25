"""manage.py seed_load: the seed-load data set of the load tests (E16-05, prompt I5-02).

Section 4 of docs/specs/07-environments.md: 20 000 licences and 500 000 activations by default.
Licences and their keys are made by the licensing domain (with audit, as an operator would);
activations go straight into the table of this module in batches. --signers activations get real
device keys: their seeds, the activation ids, the keys of --hot and --spare licences are written to
--out (JSON) for the request generator tests/load/sign.py. That file holds private keys and licence
keys: for a stand only, never in the repository; the command runs only with SEED_LOAD_ALLOWED.
"""

import json
import secrets
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.activation.models import Activation
from apps.catalog.domain import list_products
from apps.licensing.domain import create_customer, create_license, issue_key
from infra.clock import current_clock
from infra.crypto.encoding import b64url_encode
from infra.ids import new_ulid

ACTOR = "system:seed-load"
LICENSES_PER_CUSTOMER = 10
BATCH = 5000
OS = {"family": "windows", "name": "Windows 11 Pro", "version": "10.0", "arch": "x86_64"}
FP = {"scheme": "fp-v1", "components": {"disk": "d", "board": "b", "cpu": "c", "mac": "m"}}


def inn(seed: int) -> str:
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    body = f"77{seed % 10**7:07d}"
    total = sum(int(body[i]) * w for i, w in enumerate(weights))
    return body + str(total % 11 % 10)


class Command(BaseCommand):
    help = "Create the seed-load data set of the load tests (stands only)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--licenses", type=int, default=20_000)
        parser.add_argument("--activations", type=int, default=500_000)
        parser.add_argument("--signers", type=int, default=10_000)
        parser.add_argument("--hot-limit", type=int, default=100, help="licence of the race test")
        parser.add_argument("--spare", type=int, default=50, help="licences with free seats")
        parser.add_argument("--out", type=Path, required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "SEED_LOAD_ALLOWED", False):
            raise CommandError("seed_load runs on a load stand only (SEED_LOAD_ALLOWED)")
        now = current_clock().now()
        desktop = next(p for p in list_products() if p["code"] == "alteroffice-desktop")
        run = secrets.token_hex(3)
        n_licenses: int = options["licenses"]
        n_activations: int = options["activations"]
        per_license = max(1, -(-n_activations // max(n_licenses, 1)))

        def new_license(n: int, limit: int, customer_id: str) -> str:
            lic = create_license(
                {
                    "customer_id": customer_id,
                    "product_id": desktop["id"],
                    "metric_id": desktop["default_metric_id"],
                    "type": "subscription",
                    "limit": limit,
                    "valid_from": now - timedelta(days=1),
                    "valid_until": now + timedelta(days=365),
                    "enforcement": "enforce",
                },
                actor=ACTOR,
                now=now,
            )
            return str(lic.id)

        customer_id = ""
        license_ids: list[str] = []
        for n in range(n_licenses):
            if n % LICENSES_PER_CUSTOMER == 0:
                customer = create_customer(
                    {"name": f"ООО «Нагрузка {run}-{n}»", "inn": inn(n)}, actor=ACTOR, now=now
                )
                customer_id = str(customer.id)
            license_ids.append(new_license(n, per_license + 5, customer_id))
        self.stdout.write(f"{len(license_ids)} licences")

        signers: list[dict[str, str]] = []
        rows: list[Activation] = []
        made = 0
        for n in range(n_activations):
            if len(signers) < options["signers"]:
                key = Ed25519PrivateKey.generate()
                pub = key.public_key().public_bytes_raw()
            else:
                key, pub = None, secrets.token_bytes(32)
            activation_id = f"act_{new_ulid(now)}"
            rows.append(
                Activation(
                    external_id=activation_id,
                    license_id=uuid.UUID(license_ids[n % len(license_ids)]),
                    instance_id=uuid.uuid4(),
                    subject_type="device",
                    instance_name=f"WS-{n}",
                    fp_components=FP,
                    device_pubkey=b64url_encode(pub),
                    product_version="3.2.0",
                    os=OS,
                    lease_seq=1,
                    activated_at=now,
                    last_seen_at=now,
                    created_at=now,
                )
            )
            if key is not None:
                seed = key.private_bytes_raw()
                signers.append({"activation_id": activation_id, "seed": b64url_encode(seed)})
            if len(rows) == BATCH:
                Activation.objects.bulk_create(rows)
                made += len(rows)
                rows = []
        Activation.objects.bulk_create(rows)
        made += len(rows)
        self.stdout.write(f"{made} activations, {len(signers)} with device keys")

        hot_customer = create_customer(
            {"name": f"ООО «Гонка {run}»", "inn": inn(n_licenses + 1)}, actor=ACTOR, now=now
        )
        hot = new_license(-1, options["hot_limit"], str(hot_customer.id))
        spare = [new_license(-2, 1_000_000, str(hot_customer.id)) for _ in range(options["spare"])]
        out = {
            "signers": signers,
            "hot": {"license_id": hot, "key": issue_key(uuid.UUID(hot), actor=ACTOR, now=now).key},
            "spare": [issue_key(uuid.UUID(s), actor=ACTOR, now=now).key for s in spare],
        }
        options["out"].write_text(json.dumps(out), encoding="utf-8")
        options["out"].chmod(0o600)
        self.stdout.write(f"stand data in {options['out']} (private keys: keep on the stand)")
