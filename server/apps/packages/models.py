"""Local servers, quotas, packages and usage reports.

docs/specs/02-interaction-spec.md, section 13.

Licenses and customers are referenced by id only: no foreign keys to other modules.
"""

from django.db import models
from django.db.models import Q

from infra.db import ULID, UUIDModel


class ServerStatus(models.TextChoices):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


class LocalServer(UUIDModel):
    external_id = models.CharField(max_length=30, unique=True, help_text="srv_ + ULID")
    customer_id = models.UUIDField(help_text="licensing.Customer, без внешнего ключа")
    name = models.CharField(max_length=256)
    status = models.CharField(
        max_length=16, choices=ServerStatus.choices, default=ServerStatus.PENDING
    )
    public_key = models.CharField(max_length=128, blank=True, default="")
    certificate = models.TextField(blank=True, default="", help_text="JWS alm-cert+jws")
    certificate_kid = models.CharField(max_length=64, blank=True, default="")
    last_package_seq = models.PositiveIntegerField(default=0)
    last_report_seq = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    registration_code_hash = models.CharField(
        max_length=64, blank=True, default="", help_text="SHA-256 одноразового кода (E09-02)"
    )
    registration_code_expires_at = models.DateTimeField(null=True, blank=True)
    host_fingerprint = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=64, blank=True, default="")
    registered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(external_id__regex=rf"^srv_{ULID}$"), name="packages_server_external_id"
            ),
            models.CheckConstraint(
                condition=Q(status__in=ServerStatus.values), name="packages_server_status"
            ),
        ]

    def __str__(self) -> str:
        return self.external_id


class Allocation(UUIDModel):
    """Seats of a license handed over to a local server."""

    local_server = models.ForeignKey(
        LocalServer, on_delete=models.CASCADE, related_name="allocations"
    )
    license_id = models.UUIDField(help_text="licensing.License, без внешнего ключа")
    seats = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["local_server", "license_id"], name="packages_allocation_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.local_server_id}:{self.license_id}"


class Package(UUIDModel):
    local_server = models.ForeignKey(LocalServer, on_delete=models.CASCADE, related_name="packages")
    seq = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    valid_until = models.DateTimeField()
    hash = models.CharField(max_length=64, help_text="SHA-256 снимка прав без seq и дат")
    token = models.TextField(blank=True, default="", help_text="JWS alm-package+jws")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["local_server", "seq"], name="packages_package_unique_seq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.local_server_id}#{self.seq}"


class UsageReport(UUIDModel):
    local_server = models.ForeignKey(
        LocalServer, on_delete=models.CASCADE, related_name="usage_reports"
    )
    seq = models.PositiveIntegerField()
    period_from = models.DateTimeField()
    period_to = models.DateTimeField()
    data = models.JSONField(help_text="Агрегаты отчёта .alk-usage")
    receipt = models.TextField(blank=True, default="", help_text="JWS alm-receipt+jws")
    received_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["local_server", "seq"], name="packages_usagereport_unique_seq"
            )
        ]

    def __str__(self) -> str:
        return f"{self.local_server_id}#{self.seq}"


class Exchange(models.TextChoices):
    ONLINE = "online"
    FILES = "files"


class LocalIdentity(UUIDModel):
    """The local server itself (DEPLOYMENT_MODE=local, E09-01…E09-04): one row.

    The private key is a file (LOCAL_SERVER_KEY_FILE), never a column.
    """

    server_id = models.CharField(max_length=30, unique=True, help_text="srv_ + ULID")
    exchange = models.CharField(max_length=8, choices=Exchange.choices)
    central_url = models.CharField(max_length=256, blank=True, default="")
    public_key = models.CharField(max_length=64)
    certificate = models.TextField(blank=True, default="", help_text="alm-cert+jws сервера")
    issuer_chain = models.JSONField(default=list, blank=True)
    customer_id = models.UUIDField(null=True, blank=True)
    package_seq = models.PositiveIntegerField(default=0)
    package_issued_at = models.DateTimeField(null=True, blank=True)
    package_valid_until = models.DateTimeField(null=True, blank=True)
    expired_policy = models.JSONField(default=dict, blank=True)
    revoked_kids = models.JSONField(default=list, blank=True)
    # Usage reports .alk-usage (E09-05): the last report sent, its period end and the receipt
    # of the central server (online answer or the next package).
    report_seq = models.PositiveIntegerField(default=0)
    report_until = models.DateTimeField(null=True, blank=True)
    receipt_seq = models.PositiveIntegerField(default=0)
    receipt = models.TextField(blank=True, default="", help_text="alm-receipt+jws отчёта")
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(exchange__in=Exchange.values), name="packages_identity_exchange"
            ),
        ]

    def __str__(self) -> str:
        return self.server_id
