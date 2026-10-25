"""Base model for domain tables: UUID primary keys (docs/specs/06-ai-rules.md, section 4.1).

Time fields have no defaults: domain services set them from infra.clock.Clock (AGENTS.md, rule 4).
"""

import uuid

from django.db import models

ULID = "[0-9A-HJKMNP-TV-Z]{26}"


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
