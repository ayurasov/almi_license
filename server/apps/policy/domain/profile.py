"""Effective policy of a license: catalog profile + license overrides (section 8.2 of doc. 1)."""

from datetime import datetime
from typing import Any

from apps.policy.domain.engine import DAY, PolicyParams

DEFAULT_RESERVE_PCT = 3
# Fields of section 6.4 of document 2 that a catalog profile may omit (document 4, section 10).
_DEFAULTS: dict[str, Any] = {
    "restricted_caps": [],
    "restricted_days": None,
    "hard_block_mode": "read_only",
    "read_only_caps": ["view", "print", "export"],
    "offline_grace_days": None,
    "release_after_days": 30,
}


def effective_policy(params: dict[str, Any], version: int, enforcement: str) -> PolicyParams:
    """Profile params with the profile version; a non-empty enforcement of the license wins."""
    merged = _DEFAULTS | params | {"version": version}
    if enforcement:
        merged["enforcement"] = enforcement
    return PolicyParams.from_json(merged)


def reserve_pct(params: dict[str, Any], license_value: int | None) -> int:
    if license_value is not None:
        return license_value
    value = params.get("reserve_pct", DEFAULT_RESERVE_PCT)
    return int(value)


def accepts_new_activations(
    policy: PolicyParams, valid_until: datetime | None, now: datetime
) -> bool:
    """Rule 5 of section 5.2 of document 2: no new seats after term and grace, except monitor."""
    if policy.enforcement == "monitor" or valid_until is None:
        return True
    return now < valid_until + policy.grace_days * DAY


def lease_policy(policy: PolicyParams) -> dict[str, Any]:
    """The policy object of a lease (section 6.4 of document 2), lists in a stable order."""
    return {
        "version": policy.version,
        "enforcement": policy.enforcement,
        "notify_before_days": policy.notify_before_days,
        "grace_days": policy.grace_days,
        "expiry_action": policy.expiry_action,
        "restricted_caps": sorted(policy.restricted_caps),
        "restricted_days": policy.restricted_days,
        "hard_block_mode": policy.hard_block_mode,
        "read_only_caps": sorted(policy.read_only_caps),
        "offline_grace_days": policy.offline_grace_days,
        "check_interval_hours": policy.check_interval_hours,
        "release_after_days": policy.release_after_days,
    }
