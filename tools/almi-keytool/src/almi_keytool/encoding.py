"""Strict base64url, canonical JSON and key fingerprints shared by all keytool commands."""

import base64
import binascii
import hashlib
import json
import re
from typing import Any

_ALPHABET = re.compile(r"^[A-Za-z0-9_-]*$")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode unpadded base64url; anything non-canonical (padding, other characters) is an error."""
    if not _ALPHABET.match(text) or len(text) % 4 == 1:
        raise ValueError("not canonical base64url")
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except binascii.Error as error:
        raise ValueError("not canonical base64url") from error
    if b64url(data) != text:
        raise ValueError("not canonical base64url")
    return data


def canonical(obj: Any) -> bytes:
    """JSON as signed by the server and the vector generator: UTF-8, no spaces, insertion order."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def fingerprint(public_key: bytes) -> str:
    """Key fingerprint for the operations log and the ceremony protocol."""
    return "SHA256:" + b64url(hashlib.sha256(public_key).digest())
