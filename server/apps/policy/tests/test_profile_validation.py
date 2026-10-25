"""Profile rules of table 8.2 of document 1 (E01-03): pure checks without the database."""

from typing import Any

import pytest

from apps.policy.domain import profile_errors
from conftest import POLICY


def test_valid_profile_has_no_errors() -> None:
    directives = [{"id": "d1", "type": "collect_diagnostics"}]
    assert profile_errors({**POLICY, "directives": directives, "messages": {}}) == {}


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"messages": []}, "messages"),
        ({"messages": {"m1": "text"}}, "messages"),
        ({"messages": {"m1": {"text": {}, "extra": 1}}}, "messages"),
        ({"directives": [{"id": "d1"}]}, "directives"),
        ({"directives": "collect"}, "directives"),
        ({"offline_grace_days": 0}, "offline_grace_days"),
        ({"hard_block_mode": None}, "hard_block_mode"),
    ],
)
def test_invalid_parts(change: dict[str, Any], field: str) -> None:
    assert list(profile_errors({**POLICY, **change})) == [field]


def test_missing_parameters_are_reported() -> None:
    assert set(profile_errors({})) >= {"enforcement", "grace_days", "reserve_pct"}
