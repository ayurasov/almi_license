"""E16-05: manage.py seed_load makes the data set of the load tests on a stand only."""

import json
from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_refused_without_the_stand_flag(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="SEED_LOAD_ALLOWED"):
        call_command("seed_load", "--out", str(tmp_path / "stand.json"))


def test_small_data_set(settings: Any, tmp_path: Path) -> None:
    from apps.activation.models import Activation

    settings.SEED_LOAD_ALLOWED = True
    call_command("loadcatalog")
    out = tmp_path / "stand.json"
    call_command(
        "seed_load", "--licenses", "3", "--activations", "12", "--signers", "4", "--spare", "2",
        "--out", str(out),
    )  # fmt: skip
    stand = json.loads(out.read_text())
    assert len(stand["signers"]) == 4 and len(stand["spare"]) == 2
    assert Activation.objects.count() == 12
    assert oct(out.stat().st_mode & 0o777) == "0o600"
