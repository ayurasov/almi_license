"""Domain services of the compat module: adapters of products that cannot change (ADR-008)."""

from apps.compat.domain.ids import os_node_id, server_instance_id
from apps.compat.domain.legacy_activate import LegacyResult, legacy_activate
from apps.compat.domain.nextcloud import SubscriptionNotFound, SubscriptionRequest, subscription

__all__ = [
    "LegacyResult",
    "legacy_activate",
    "SubscriptionNotFound",
    "SubscriptionRequest",
    "os_node_id",
    "server_instance_id",
    "subscription",
]
