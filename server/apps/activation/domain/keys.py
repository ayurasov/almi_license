"""Device keys of activations: request signatures are checked with them (E05-01)."""

from apps.activation.models import Activation


def device_public_key(activation_id: str) -> str | None:
    """base64url Ed25519 key of the activation in any status; None for an unknown id.

    The status is checked by the requested operation (released -> 410, revoked -> 403).
    """
    return (
        Activation.objects.filter(external_id=activation_id)
        .values_list("device_pubkey", flat=True)
        .first()
    )
