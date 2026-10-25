"""Fingerprint tolerance, scheme fp-v1 (section 2.4 of document 2, ADR-005).

At least 3 of 4 components match; a component that is unknown on either side (value "unknown"
or absent) is not counted, and then at least 2 of the counted ones must match. With fewer than
two components to compare the fingerprint is out of tolerance.
"""

COMPONENTS = ("disk", "board", "cpu", "mac")
UNKNOWN = "unknown"


def within_tolerance(stored: dict[str, str], presented: dict[str, str]) -> bool:
    counted = [
        name
        for name in COMPONENTS
        if stored.get(name, UNKNOWN) != UNKNOWN and presented.get(name, UNKNOWN) != UNKNOWN
    ]
    if len(counted) < 2:
        return False
    required = 3 if len(counted) == len(COMPONENTS) else 2
    return sum(stored[name] == presented[name] for name in counted) >= required
