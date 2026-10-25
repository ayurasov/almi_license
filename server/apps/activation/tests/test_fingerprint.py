"""Fingerprint tolerance fp-v1 (section 2.4 of document 2): 3 of 4, unknown is not counted."""

import pytest

from apps.activation.domain.fingerprint import within_tolerance

BASE = {"disk": "d", "board": "b", "cpu": "c", "mac": "m"}


@pytest.mark.parametrize(
    ("other", "expected"),
    [
        (BASE, True),
        (BASE | {"mac": "x"}, True),  # 3 of 4
        (BASE | {"mac": "x", "cpu": "y"}, False),  # 2 of 4
        (BASE | {"mac": "unknown"}, True),  # 3 of 3 counted
        (BASE | {"mac": "unknown", "cpu": "y"}, True),  # 2 of 3
        (BASE | {"mac": "unknown", "cpu": "y", "disk": "z"}, False),  # 1 of 3
        (BASE | {"mac": "unknown", "cpu": "unknown"}, True),  # 2 of 2
        (BASE | {"mac": "unknown", "cpu": "unknown", "disk": "z"}, False),  # 1 of 2
        ({"disk": "unknown", "board": "unknown", "cpu": "unknown", "mac": "m"}, False),
        ({"disk": "d", "board": "b", "cpu": "c"}, True),  # a missing component is unknown
        ({}, False),
    ],
)
def test_tolerance(other: dict[str, str], expected: bool) -> None:
    assert within_tolerance(BASE, other) is expected
    assert within_tolerance(other, BASE) is expected


def test_unknown_on_the_stored_side_is_not_counted() -> None:
    stored = BASE | {"cpu": "unknown"}
    assert within_tolerance(stored, BASE | {"mac": "x"})
    assert not within_tolerance(stored, BASE | {"mac": "x", "disk": "y"})
