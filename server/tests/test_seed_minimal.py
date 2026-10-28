"""manage.py seed_minimal (section 4 of document 7): ten licences, their keys in a file."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps.licensing.domain import (
    inn_is_valid,
    key_hash,
    key_mask,
    license_id_by_key_hash,
    list_customers,
)

pytestmark = pytest.mark.django_db


def test_seed_minimal_creates_the_set_once(tmp_path: Path) -> None:
    call_command("loadcatalog", stdout=StringIO())
    out = tmp_path / "keys.json"
    printed = StringIO()
    call_command("seed_minimal", "--trial", "--out", str(out), stdout=printed)
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 10
    assert {r["product"] for r in rows} == {"alteroffice-desktop", "alteroffice-web", "alteros"}
    assert {r["type"] for r in rows} == {"subscription", "perpetual", "trial", "nfr", "free"}
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    for row in rows:
        assert license_id_by_key_hash(key_hash(row["key"])) is not None
        # Rule 9 of AGENTS.md: only masks reach the output.
        assert row["key"] not in printed.getvalue()
        assert key_mask(row["key"]) in printed.getvalue()
    customers = list_customers(name="Тестовый заказчик").results
    assert len(customers) == 3 and all(inn_is_valid(c.inn) for c in customers)

    again = StringIO()
    call_command("seed_minimal", "--trial", "--out", str(tmp_path / "second.json"), stdout=again)
    assert "nothing changed" in again.getvalue()
    assert list_customers(name="Тестовый заказчик").count == 3


def test_seed_minimal_needs_the_trial_flag(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="--trial"):
        call_command("seed_minimal", "--out", str(tmp_path / "k.json"))


def test_seed_minimal_to_stdout_keeps_masks_apart() -> None:
    call_command("loadcatalog", stdout=StringIO())
    out, err = StringIO(), StringIO()
    call_command("seed_minimal", "--trial", "--out", "-", stdout=out, stderr=err)
    rows = json.loads(out.getvalue())
    assert len(rows) == 10
    assert all(row["key"] not in err.getvalue() for row in rows)
    assert "10 licences" in err.getvalue()
