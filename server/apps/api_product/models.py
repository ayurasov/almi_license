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
