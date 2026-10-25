"""Activations and their latest leases (docs/specs/01-architecture.md, sections 7.1 and 7.4).

References to licensing are the only foreign keys to another module (docs/decisions.md, I1-03).
"""

from django.db import models
from django.db.models import Q

from infra.db import ULID, UUIDModel


class ActivationStatus(models.TextChoices):
    ACTIVE = "active"
    RELEASED = "released"
    RELEASED_AUTO = "released_auto"
    REVOKED = "revoked"
    CONFLICT = "conflict"


class SubjectType(models.TextChoices):
    DEVICE = "device"
    SERVER_INSTANCE = "server_instance"
    OS_NODE = "os_node"


class Activation(UUIDModel):
    external_id = models.CharField(max_length=30, unique=True, help_text="act_ + ULID")
    license = models.ForeignKey("licensing.License", on_delete=models.PROTECT, related_name="+")
    instance_id = models.UUIDField()
    subject_type = models.CharField(max_length=16, choices=SubjectType.choices)
    instance_name = models.CharField(max_length=128, blank=True, default="")
    fp_components = models.JSONField(
        help_text="Схема и хэши компонентов отпечатка; сырые значения не хранятся"
    )
    device_pubkey = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16, choices=ActivationStatus.choices, default=ActivationStatus.ACTIVE
    )
    in_reserve = models.BooleanField(default=False)
    product_version = models.CharField(max_length=64)
    os = models.JSONField()
    lease_seq = models.PositiveIntegerField(default=0)
    offline = models.BooleanField(
        default=False, help_text="Последняя связь — файлом .alk-req (портал офлайн-активации)"
    )
    done_profile_directives = models.JSONField(
        default=list,
        blank=True,
        help_text="id директив профиля, подтверждённых или неподдерживаемых",
    )
    activated_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    release_receipt = models.TextField(
        blank=True, default="", help_text="alm-receipt+jws: a repeated release returns it (E03-05)"
    )
    created_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "last_seen_at"], name="activation_status_last_seen")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["license", "instance_id"],
                condition=Q(status="active"),
                name="activation_one_active_instance",
            ),
            models.CheckConstraint(
                condition=Q(external_id__regex=rf"^act_{ULID}$"), name="activation_external_id"
            ),
            models.CheckConstraint(
                condition=Q(status__in=ActivationStatus.values), name="activation_status"
            ),
            models.CheckConstraint(
                condition=Q(subject_type__in=SubjectType.values), name="activation_subject_type"
            ),
        ]

    def __str__(self) -> str:
        return self.external_id


class Lease(UUIDModel):
    """The latest lease issued for an activation.

    Only its hash is kept; the JWS itself goes to the product.
    """

    activation = models.OneToOneField(Activation, on_delete=models.CASCADE, related_name="lease")
    seq = models.PositiveIntegerField()
    issued_at = models.DateTimeField()
    exp = models.DateTimeField(
        null=True, blank=True, help_text="Пусто — без срока доверия без связи"
    )
    jws_hash = models.CharField(max_length=64)

    def __str__(self) -> str:
        return f"{self.activation_id}#{self.seq}"


class Directive(UUIDModel):
    """A directive queued for an activation (section 8 of document 2); sent until acked."""

    external_id = models.CharField(max_length=30, unique=True, help_text="dir_ + ULID")
    activation = models.ForeignKey(Activation, on_delete=models.CASCADE, related_name="directives")
    type = models.CharField(max_length=32)
    params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField()
    acked_at = models.DateTimeField(null=True, blank=True)
    unsupported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["activation", "acked_at"], name="activation_directive_open")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(external_id__regex=rf"^dir_{ULID}$"), name="activation_directive_id"
            ),
        ]

    def __str__(self) -> str:
        return self.external_id


class ProductEvent(UUIDModel):
    """An event reported by the product (POST /api/v1/events, section 4 of document 2).

    The id is chosen by the module, so a repeated delivery is stored once.
    """

    activation = models.ForeignKey(Activation, on_delete=models.CASCADE, related_name="events")
    event_id = models.CharField(max_length=64)
    type = models.CharField(max_length=64)
    at = models.DateTimeField()
    data = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["activation", "event_id"], name="activation_event_once")
        ]
        indexes = [models.Index(fields=["type", "at"], name="activation_event_type_at")]

    def __str__(self) -> str:
        return f"{self.type}@{self.at}"
