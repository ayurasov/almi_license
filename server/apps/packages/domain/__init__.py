"""Domain services of the packages module: local servers, quotas, packages (doc. 2, s. 13)."""

from uuid import UUID

from apps.packages.domain.servers import (
    IssuedCode,
    Registration,
    ServerData,
    alk_file,
    allocated_seats,
    create_server,
    list_servers,
    new_code,
    package_since,
    register,
    register_from_file,
    server_public_key,
    set_allocations,
)
from apps.packages.models import Allocation


def license_allocated(license_id: UUID) -> bool:
    """Seats of the license are handed over to a local server (blocks a transfer, E01-08)."""
    return Allocation.objects.filter(license_id=license_id, seats__gt=0).exists()


__all__ = [
    "IssuedCode",
    "Registration",
    "ServerData",
    "alk_file",
    "allocated_seats",
    "create_server",
    "license_allocated",
    "list_servers",
    "new_code",
    "package_since",
    "register",
    "register_from_file",
    "server_public_key",
    "set_allocations",
]
