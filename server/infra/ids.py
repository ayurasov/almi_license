"""ULID identifiers for external ids act_ and srv_ (section 3 of document 2).

48-bit millisecond time from the caller's Clock and 80 random bits (not a secret).
"""

import secrets
from datetime import datetime

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(at: datetime) -> str:
    milliseconds = int(at.timestamp() * 1000)
    if not 0 <= milliseconds < 1 << 48:
        raise ValueError("time is outside the ULID range")
    value = (milliseconds << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    return "".join(CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))
