"""Models of the api_product module (tables are owned by this module only)."""

from django.db import models

from infra.db import UUIDModel


class RequestNonce(UUIDModel):
    """nonce of a signed request, kept for the replay window (section 4.4 of document 2)."""

    keyid = models.CharField(max_length=64)
    nonce = models.CharField(max_length=22, help_text="16 bytes, base64url")
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["keyid", "nonce"], name="request_nonce_unique")
        ]
        indexes = [models.Index(fields=["created_at"], name="request_nonce_created")]

    def __str__(self) -> str:
        return self.keyid


class IdempotencyRecord(UUIDModel):
    """The first response to a request with an Idempotency-Key, kept 24 hours (E05-02)."""

    scope = models.CharField(max_length=64, help_text="открытый ключ подписи запроса")
    key = models.CharField(max_length=64)
    path = models.CharField(max_length=256)
    body_hash = models.CharField(max_length=64)
    status = models.PositiveSmallIntegerField()
    content_type = models.CharField(max_length=64)
    response = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "key"], name="idempotency_unique_key")
        ]


class RateCounter(UUIDModel):
    """Requests of one key in one fixed window (section 4.7 of document 2).

    A counter is shared by all processes of the server, unlike the cache of LK 2.0 (document 8,
    section 3.2). Keys never hold a licence key or an IP in clear: callers pass a hash.
    """

    key = models.CharField(max_length=128)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "window_start"], name="rate_counter_window")
        ]
        indexes = [models.Index(fields=["window_start"], name="rate_counter_start")]

    def __str__(self) -> str:
        return self.key


class RateBlock(UUIDModel):
    """A key blocked until a moment (legacy /api/activate/: an IP after repeated errors)."""

    key = models.CharField(max_length=128, unique=True)
    until = models.DateTimeField()

    def __str__(self) -> str:
        return self.key
