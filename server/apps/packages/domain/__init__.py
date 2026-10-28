"""Domain services of the packages module: local servers, quotas, packages (doc. 2, s. 13)."""

from uuid import UUID

from apps.packages.domain.local import (
    LocalStatus,
    SetupResult,
    import_package,
    local_server_id,
    local_status,
    package_terms,
    setup,
    sync_package,
)
from apps.packages.domain.local_usage import ReportState, build_report, report_state, send_report
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
from apps.packages.domain.usage import UsageReceipt, accept_usage, gunzip_report, local_active
from apps.packages.models import Allocation


def license_allocated(license_id: UUID) -> bool:
    """Seats of the license are handed over to a local server (blocks a transfer, E01-08)."""
    return Allocation.objects.filter(license_id=license_id, seats__gt=0).exists()


__all__ = [
    "gunzip_report",
    "ReportState",
    "UsageReceipt",
    "accept_usage",
    "build_report",
    "local_active",
    "report_state",
    "send_report",
    "LocalStatus",
    "SetupResult",
    "import_package",
    "local_server_id",
    "local_status",
    "package_terms",
    "setup",
    "sync_package",
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
