"""PolicyEngine on every reference vector contracts/vectors/policy/*.json (E04-01).

The vectors are the contract: a mismatch is a bug in the engine, never in the vector (P12).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from apps.policy.domain.engine import LicenseFacts, PolicyParams, TrialFacts, evaluate
from tests.vectors import VECTORS


def vectors() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VECTORS / "policy").glob("*.json"))
    ]


def instant(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def facts(vector: dict[str, Any]) -> LicenseFacts | TrialFacts:
    license_ = vector["license"]
    if license_ is None:
        trial = vector["trial"]
        return TrialFacts(
            first_launch=instant(trial["first_launch"]),
            product_capabilities=frozenset(trial["product_capabilities"]),
        )
    return LicenseFacts(
        type=license_["type"],
        status=license_["status"],
        valid_until=instant(license_["valid_until"]),
        support_until=instant(license_["support_until"]),
        capabilities=frozenset(license_["capabilities"]),
    )


def test_all_vectors_are_present() -> None:
    assert len(vectors()) == 39
    assert Path(VECTORS / "policy").is_dir()


@pytest.mark.parametrize("vector", vectors(), ids=lambda v: v["name"])
def test_vector(vector: dict[str, Any]) -> None:
    now = instant(vector["now"])
    assert now is not None

    result = evaluate(
        PolicyParams.from_json(vector["policy"]),
        facts(vector),
        now,
        instant(vector["last_success_at"]),
    )

    expected = vector["expected"]
    assert result.state == expected["state"]
    assert result.capabilities == frozenset(expected["capabilities"])
    assert result.message_ids == tuple(expected["messages_ids"])
    assert result.lease_exp == instant(expected["lease_exp"])
