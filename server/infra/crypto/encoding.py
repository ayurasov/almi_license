"""Strict base64url without padding (RFC 7515, section 2)."""

import base64
import binascii
import re

_ALPHABET = re.compile(r"[A-Za-z0-9_-]*")


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode canonical unpadded base64url; anything else raises ValueError."""
    if not _ALPHABET.fullmatch(text) or len(text) % 4 == 1:
        raise ValueError("not base64url")
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except binascii.Error:
        raise ValueError("not base64url") from None
    if b64url_encode(data) != text:  # non-zero trailing bits
        raise ValueError("not base64url")
    return data
