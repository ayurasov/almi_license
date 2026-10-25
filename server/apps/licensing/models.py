"""Licensing: customers, licenses, keys (docs/specs/01-architecture.md, sections 7.1, 7.2, 7.5).

References to catalog are the only foreign keys to another module (docs/decisions.md, I1-03).
"""

from django.db import models
from django.db.models import F, Q

from infra.db import UUIDModel


class CustomerStatus(models.TextChoices):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Customer(UUIDModel):
    name = models.CharField(max_length=512)
    inn = models.CharField(
        max_length=12, blank=True, default="", help_text="Пусто — заказчик без ИНН"
    )
    external_id = models.CharField(
        max_length=128, blank=True, default="", help_text="Идентификатор в ЛК"
    )
    contact = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=8,
        choices=CustomerStatus.choices,
        default=CustomerStatus.ACTIVE,
        help_text="Архивный заказчик не выбирается для новых лицензий; удаления нет",
    )
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CustomerStatus.values), name="licensing_customer_status"
            ),
            models.UniqueConstraint(
                fields=["inn"], condition=~Q(inn=""), name="licensing_customer_unique_inn"
            ),
            models.UniqueConstraint(
                fields=["external_id"],
                condition=~Q(external_id=""),
                name="licensing_customer_unique_external_id",
            ),
            models.CheckConstraint(
                condition=Q(inn="") | Q(inn__regex=r"^[0-9]{10}([0-9]{2})?$"),
                name="licensing_customer_inn_format",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class LicenseType(models.TextChoices):
    SUBSCRIPTION = "subscription"
    PERPETUAL = "perpetual"
    TRIAL = "trial"
    NFR = "nfr"
    FREE = "free"


class LicenseStatus(models.TextChoices):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class Enforcement(models.TextChoices):
    ENFORCE = "enforce"
    MONITOR = "monitor"


class License(UUIDModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="licenses")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    edition = models.ForeignKey(
        "catalog.Edition", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    metric = models.ForeignKey("catalog.Metric", on_delete=models.PROTECT, related_name="+")
    type = models.CharField(max_length=16, choices=LicenseType.choices)
    limit = models.PositiveIntegerField()
    reserve_pct = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Пусто — из профиля"
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True, help_text="Пусто — бессрочно")
    support_until = models.DateTimeField(null=True, blank=True)
    policy_profile_code = models.CharField(
        max_length=128, blank=True, default="", help_text="Пусто — по каталогу"
    )
    enforcement = models.CharField(
        max_length=8,
        choices=Enforcement.choices,
        blank=True,
        default="",
        help_text="Пусто — из профиля",
    )
    extra_capabilities = models.JSONField(default=list, blank=True)
    state = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="Состояние по PolicyEngine на state_at: ежечасный пересчёт (E12-03)",
    )
    state_at = models.DateTimeField(null=True, blank=True)
    limits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Лимиты пользователей: named_users, active_users, only_count_active",
    )
    status = models.CharField(
        max_length=16, choices=LicenseStatus.choices, default=LicenseStatus.ACTIVE
    )
    rights_version = models.PositiveIntegerField(
        default=1, help_text="Растёт при продлении и снятии блока (E01-05)"
    )
    monitor_until = models.DateTimeField(
        null=True, blank=True, help_text="Снятый блок: режим monitor до этого момента (E01-05)"
    )
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "valid_until"], name="licensing_license_status_until")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(type__in=LicenseType.values), name="licensing_license_type"
            ),
            models.CheckConstraint(
                condition=Q(status__in=LicenseStatus.values), name="licensing_license_status"
            ),
            models.CheckConstraint(
                condition=Q(enforcement__in=["", *Enforcement.values]),
                name="licensing_license_enforcement",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
                name="licensing_license_dates",
            ),
            models.CheckConstraint(
                condition=Q(reserve_pct__isnull=True) | Q(reserve_pct__lte=100),
                name="licensing_license_reserve_pct",
            ),
        ]

    def __str__(self) -> str:
        return str(self.id)


class KeyFormat(models.TextChoices):
    LEGACY = "legacy"
    V1 = "v1"


class LicenseKey(UUIDModel):
    """A key is stored as a hash and a mask only; the full key never reaches the database."""

    license = models.ForeignKey(License, on_delete=models.PROTECT, related_name="keys")
    key_hash = models.CharField(max_length=64, unique=True)
    key_mask = models.CharField(max_length=19)
    format = models.CharField(max_length=8, choices=KeyFormat.choices)
    order_no = models.CharField(max_length=64, blank=True, default="")
    article = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(key_mask__regex=r"^[0-9A-Z]{4}-\*{4}-\*{4}-[0-9A-Z]{4}$"),
                name="licensing_licensekey_mask",
            ),
            models.CheckConstraint(
                condition=Q(format__in=KeyFormat.values), name="licensing_licensekey_format"
            ),
        ]

    def __str__(self) -> str:
        return self.key_mask


class ExternalRef(UUIDModel):
    """Identifier of the license in an external system: the LK serial number YY-ARTICLE-DDD-NNNN."""

    license = models.ForeignKey(License, on_delete=models.CASCADE, related_name="external_refs")
    system = models.CharField(max_length=32, default="lk")
    value = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system", "value"], name="licensing_externalref_unique")
        ]

    def __str__(self) -> str:
        return f"{self.system}:{self.value}"


class ArticleMapping(UUIDModel):
    """Field AA of an LK article -> product, edition, metric (section 8.2 of document 4, E06-02)."""

    aa = models.CharField(max_length=8, unique=True)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    edition = models.ForeignKey(
        "catalog.Edition", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    metric = models.ForeignKey("catalog.Metric", on_delete=models.PROTECT, related_name="+")

    def __str__(self) -> str:
        return self.aa


class ImportSessionStatus(models.TextChoices):
    DRAFT = "draft"
    APPLIED = "applied"
    EXPIRED = "expired"


class ImportSession(UUIDModel):
    """Preview of an LK export (E06-01): rows with status and reasons; keys only as mask/hash."""

    filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=8, choices=ImportSessionStatus.choices, default=ImportSessionStatus.DRAFT
    )
    rows = models.JSONField()
    summary = models.JSONField()
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ImportSessionStatus.values),
                name="licensing_importsession_status",
            )
        ]

    def __str__(self) -> str:
        return self.filename
