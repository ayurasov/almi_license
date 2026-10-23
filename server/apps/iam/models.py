"""Models of the iam module (tables are owned by this module only).

Console users are django.contrib.auth users; Account adds the role and the lockout state (E07-02).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from infra.db import UUIDModel


class Role(models.TextChoices):
    OPERATOR = "operator"
    ADMIN = "admin"
    CUSTOMER_VIEWER = "customer_viewer"


class Account(UUIDModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(role__in=Role.values), name="iam_account_role")
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role}"
