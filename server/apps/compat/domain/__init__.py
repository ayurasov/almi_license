"""Domain services of the compat module: adapters of products that cannot change (ADR-008)."""

from apps.compat.domain.ids import os_node_id, server_instance_id
from apps.compat.domain.nextcloud import SubscriptionNotFound, SubscriptionRequest, subscription

__all__ = [
    "SubscriptionNotFound",
    "SubscriptionRequest",
    "os_node_id",
    "server_instance_id",
    "subscription",
]
