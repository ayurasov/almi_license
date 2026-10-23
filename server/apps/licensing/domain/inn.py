"""INN check digits: 10 digits for organisations, 12 for individual entrepreneurs."""

_W10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_W11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_W12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


def _digit(digits: list[int], weights: tuple[int, ...]) -> int:
    return sum(d * w for d, w in zip(digits, weights, strict=False)) % 11 % 10


def inn_is_valid(inn: str) -> bool:
    if not (inn.isascii() and inn.isdigit() and len(inn) in (10, 12)):
        return False
    digits = [int(c) for c in inn]
    if len(digits) == 10:
        return _digit(digits, _W10) == digits[9]
    return _digit(digits, _W11) == digits[10] and _digit(digits, _W12) == digits[11]
