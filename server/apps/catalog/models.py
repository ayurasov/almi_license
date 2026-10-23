"""Catalog: products, editions, capabilities, metrics, policy profiles.

docs/specs/04-catalog.md
"""

from django.db import models
from django.db.models import Q

from infra.db import UUIDModel


class SubjectType(models.TextChoices):
    DEVICE = "device"
    SERVER_INSTANCE = "server_instance"
    OS_NODE = "os_node"


class Metric(UUIDModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.JSONField(default=dict)

    def __str__(self) -> str:
        return self.code


class ProductStatus(models.TextChoices):
    ACTIVE = "active"
    RESERVED = "reserved"
    DEPRECATED = "deprecated"


class Product(UUIDModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.JSONField(default=dict)
    default_metric = models.ForeignKey(Metric, on_delete=models.PROTECT, related_name="+")
    subject_type = models.CharField(max_length=16, choices=SubjectType.choices)
    default_profile_code = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=ProductStatus.choices, default=ProductStatus.ACTIVE
    )
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9-]{2,64}$"), name="catalog_product_code_format"
            ),
            models.CheckConstraint(
                condition=Q(subject_type__in=SubjectType.values), name="catalog_product_subject"
            ),
            models.CheckConstraint(
                condition=Q(status__in=ProductStatus.values), name="catalog_product_status"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class CapabilityStatus(models.TextChoices):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class Capability(UUIDModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="capabilities")
    code = models.CharField(max_length=48)
    name = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=CapabilityStatus.choices, default=CapabilityStatus.ACTIVE
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "code"], name="catalog_capability_unique_code"
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^([a-z0-9_]{2,48}|app:[a-z0-9_-]{1,44})$"),
                name="catalog_capability_code",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CapabilityStatus.values), name="catalog_capability_status"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class Edition(UUIDModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="editions")
    code = models.CharField(max_length=32)
    name = models.JSONField(default=dict)
    base_capabilities = models.ManyToManyField(Capability, related_name="editions", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "code"], name="catalog_edition_unique_code"),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9-]{2,32}$"), name="catalog_edition_code"
            ),
        ]

    def __str__(self) -> str:
        return self.code


class PolicyProfile(UUIDModel):
    """Versioned profile: a change is a new row with the next version (E01-03)."""

    code = models.CharField(max_length=128)
    version = models.PositiveIntegerField()
    params = models.JSONField()
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"], name="catalog_policyprofile_unique_version"
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1), name="catalog_policyprofile_version_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version}"
