"""Idempotency-Key of the Product API (E05-02; section 4 of document 2, IdempotencyStore).

A repeat with the same key and body within 24 hours gets the first response as it was; the same
key with another body is 409 idempotency_conflict. Keys are scoped by the public key that signed
the request, so one device cannot replay another's response. Server errors (5xx) are not kept: the
client may try again with the same key.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction

from apps.api_product.models import IdempotencyRecord

WINDOW = timedelta(hours=24)
KEY = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
SERVER_ERROR = 500


class InvalidKey(ValueError):
    """The header is not a UUID (400 invalid_request)."""


class KeyConflict(Exception):
    """The key was used with another body (409 idempotency_conflict)."""


@dataclass(frozen=True)
class Stored:
    status: int
    content_type: str
    body: bytes


def _digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def replay(scope: str, key: str, body: bytes, *, now: datetime) -> Stored | None:
    """The kept response for this key, or None when the request is new."""
    if not KEY.fullmatch(key):
        raise InvalidKey(key)
    row = IdempotencyRecord.objects.filter(
        scope=scope, key=key.lower(), created_at__gte=now - WINDOW
    ).first()
    if row is None:
        return None
    if row.body_hash != _digest(body):
        raise KeyConflict(key)
    return Stored(row.status, row.content_type, row.response.encode("utf-8"))


def remember(
    scope: str, key: str, path: str, body: bytes, stored: Stored, *, now: datetime
) -> None:
    if stored.status >= SERVER_ERROR:
        return
    IdempotencyRecord.objects.filter(
        scope=scope, key=key.lower(), created_at__lt=now - WINDOW
    ).delete()
    try:
        with transaction.atomic():
            IdempotencyRecord.objects.create(
                scope=scope,
                key=key.lower(),
                path=path[:256],
                body_hash=_digest(body),
                status=stored.status,
                content_type=stored.content_type[:64],
                response=stored.body.decode("utf-8"),
                created_at=now,
            )
    except IntegrityError:
        # A concurrent request with the same key was first; its response is the kept one.
        pass


def purge(now: datetime) -> int:
    """Delete records older than the window; run by the background job (E12-01)."""
    deleted, _ = IdempotencyRecord.objects.filter(created_at__lt=now - WINDOW).delete()
    return deleted
