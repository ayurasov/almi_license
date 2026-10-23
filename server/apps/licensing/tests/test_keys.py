"""License key normalisation and hash (section 2 and 10 of document 2; decision 23.10.2026)."""

import hashlib

import pytest

from apps.licensing.domain import InvalidKeyFormat, key_hash, normalize_key


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("2645-7KQ9-MX2D-81ZT", "2645-7KQ9-MX2D-81ZT"),
        (" 2645-7kq9-mx2d-81zt\n", "2645-7KQ9-MX2D-81ZT"),
        ("2645 - 7KQ9 - MX2D - 81ZT", "2645-7KQ9-MX2D-81ZT"),
        ("ABCD-EFGH-JKLM-NPQR", "ABCD-EFGH-JKLM-NPQR"),
    ],
)
def test_normalize(raw: str, normal: str) -> None:
    assert normalize_key(raw) == normal


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "2645-7KQ9-MX2D",
        "26457KQ9MX2D81ZT",
        "2645_7KQ9_MX2D_81ZT",
        "2645-7KQ9-MX2D-81Z!",
        "2645-7KQ9-MX2D-81ZT-0000",
        "２６４５-7KQ9-MX2D-81ZT",
    ],
)
def test_malformed(raw: str) -> None:
    with pytest.raises(InvalidKeyFormat):
        normalize_key(raw)


def test_hash_is_sha256_of_the_normalised_key() -> None:
    expected = hashlib.sha256(b"2645-7KQ9-MX2D-81ZT").hexdigest()
    assert key_hash("2645-7kq9-mx2d-81zt") == expected
    assert len(expected) == 64
