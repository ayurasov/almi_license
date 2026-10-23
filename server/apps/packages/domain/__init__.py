"""Domain services of the packages module."""

from uuid import UUID

from apps.packages.models import Allocation


def license_allocated(license_id: UUID) -> bool:
    """Seats of the license are handed over to a local server (blocks a transfer, E01-08)."""
    return Allocation.objects.filter(license_id=license_id, seats__gt=0).exists()


__all__ = ["license_allocated"]
