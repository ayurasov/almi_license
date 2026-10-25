"""License keys: normalisation and hash (section 2 of document 2; decision of 23.10.2026).

The full key never reaches the database or logs: only key_hash (hex SHA-256 of the normalised
key, the same value as keys[].key_hash of a .alk package) and the mask are stored.
"""

import hashlib
import re

_FORMAT = re.compile(r"[0-9A-Z]{4}(-[0-9A-Z]{4}){3}")


class InvalidKeyFormat(ValueError):
    """400 invalid_key_format."""


def normalize_key(raw: str) -> str:
    """Upper case without whitespace; WWyy-XXXX-XXXX-XXXX and XXXX-XXXX-XXXX-XXXX."""
    key = "".join(raw.split()).upper()
    if not key.isascii() or _FORMAT.fullmatch(key) is None:
        raise InvalidKeyFormat("license key format")
    return key


def key_hash(raw: str) -> str:
    return hashlib.sha256(normalize_key(raw).encode("ascii")).hexdigest()


def key_mask(raw: str) -> str:
    key = normalize_key(raw)
    return f"{key[:4]}-****-****-{key[-4:]}"
