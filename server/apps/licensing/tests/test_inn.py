"""INN check digits (Russian tax number: 10 digits for companies, 12 for individuals)."""

import pytest

from apps.licensing.domain import inn_is_valid


@pytest.mark.parametrize("inn", ["7707083893", "7736207543", "500100732259", "773370857141"])
def test_valid(inn: str) -> None:
    assert inn_is_valid(inn)


@pytest.mark.parametrize(
    "inn",
    ["7707083894", "500100732258", "500100732249", "770708389", "77070838931", "", "77O7083893"],
)
def test_invalid(inn: str) -> None:
    assert not inn_is_valid(inn)
