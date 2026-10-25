"""PolicyEngine: license state from the lease data (E04-01).

Algorithm of section 7.2 of document 2 and section 8 of document 1, with the rules of
decision 12 (contracts/vectors/README.md, "policy"). The same algorithm runs in the DL module
(StateEvaluator); both pass contracts/vectors/policy.

A pure function (AGENTS.md, rule 5): no Django, database, network, system time or randomness.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

DAY = timedelta(days=1)
TRIAL_DAYS = 30
TRIAL_ENDING_DAYS = 5
NOTICE_DIALOG_DAYS = 7
SUPPORT = "support"
UPDATES = "updates"


class State(StrEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    UNLICENSED = "UNLICENSED"
    RESTRICTED = "RESTRICTED"
    REVOKED = "REVOKED"
    NOTICE = "NOTICE"
    GRACE = "GRACE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PolicyParams:
    """Policy profile, section 6.4 of document 2."""

    version: int
    enforcement: str  # enforce | monitor
    notify_before_days: int
    grace_days: int
    expiry_action: str  # none | restrict | block
    restricted_caps: frozenset[str]
    restricted_days: int | None
    hard_block_mode: str  # read_only | no_start
    read_only_caps: frozenset[str]
    offline_grace_days: int | None
    check_interval_hours: int
    release_after_days: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PolicyParams":
        return cls(
            version=data["version"],
            enforcement=data["enforcement"],
            notify_before_days=data["notify_before_days"],
            grace_days=data["grace_days"],
            expiry_action=data["expiry_action"],
            restricted_caps=frozenset(data["restricted_caps"]),
            restricted_days=data["restricted_days"],
            hard_block_mode=data["hard_block_mode"],
            read_only_caps=frozenset(data["read_only_caps"]),
            offline_grace_days=data["offline_grace_days"],
            check_interval_hours=data["check_interval_hours"],
            release_after_days=data["release_after_days"],
        )


@dataclass(frozen=True)
class LicenseFacts:
    """License part of the lease (lic.* and capabilities, section 6.2 of document 2)."""

    type: str  # subscription | perpetual | trial | nfr | free
    status: str  # active | suspended | revoked
    valid_until: datetime | None
    support_until: datetime | None
    capabilities: frozenset[str]


@dataclass(frozen=True)
class TrialFacts:
    """No lease: the product's own trial (first launch, all functions of the product)."""

    first_launch: datetime | None
    product_capabilities: frozenset[str]


@dataclass(frozen=True)
class PolicyResult:
    state: State
    capabilities: frozenset[str]
    message_ids: tuple[str, ...]
    lease_exp: datetime | None
    next_check_at: datetime | None


def _require_aware(*moments: datetime | None) -> None:
    for moment in moments:
        if moment is not None and moment.utcoffset() is None:
            raise ValueError("datetimes must carry a timezone")


def _days_left(until: datetime, now: datetime) -> int:
    """Whole days remaining, rounded up (rule 5 of decision 12)."""
    return math.ceil((until - now) / DAY)


def _trial(facts: TrialFacts, now: datetime) -> PolicyResult:
    capabilities = facts.product_capabilities - {SUPPORT}
    end = None if facts.first_launch is None else facts.first_launch + TRIAL_DAYS * DAY
    if end is not None and now >= end:
        return PolicyResult(State.UNLICENSED, capabilities, ("unlicensed.start",), None, None)
    days_left = TRIAL_DAYS if end is None else _days_left(end, now)
    messages = (
        ("trial.banner", "trial.ending") if days_left <= TRIAL_ENDING_DAYS else ("trial.banner",)
    )
    return PolicyResult(State.TRIAL, capabilities, messages, None, None)


def _after_term(policy: PolicyParams, valid_until: datetime | None, now: datetime) -> State:
    if policy.expiry_action == "none":
        return State.GRACE
    if policy.expiry_action == "block":
        return State.BLOCKED
    if (
        policy.restricted_days is not None
        and valid_until is not None
        and now >= valid_until + (policy.grace_days + policy.restricted_days) * DAY
    ):
        return State.BLOCKED
    return State.RESTRICTED


def _state(
    policy: PolicyParams, facts: LicenseFacts, now: datetime, last_success_at: datetime | None
) -> State:
    valid_until = facts.valid_until
    if facts.status == "revoked":
        return State.REVOKED
    if (
        policy.offline_grace_days is not None
        and last_success_at is not None
        and now > last_success_at + policy.offline_grace_days * DAY
    ):
        return _after_term(policy, valid_until, now)
    if valid_until is None or now < valid_until - policy.notify_before_days * DAY:
        return State.ACTIVE
    if now < valid_until:
        return State.NOTICE
    if now < valid_until + policy.grace_days * DAY:
        return State.GRACE
    return _after_term(policy, valid_until, now)


def _capabilities(
    policy: PolicyParams, facts: LicenseFacts, state: State, now: datetime
) -> frozenset[str]:
    if policy.enforcement == "monitor":
        return facts.capabilities
    if state in (State.BLOCKED, State.REVOKED):
        return frozenset() if policy.hard_block_mode == "no_start" else policy.read_only_caps
    capabilities = facts.capabilities
    if state == State.RESTRICTED:
        capabilities -= policy.restricted_caps
    if facts.support_until is not None and now >= facts.support_until:
        capabilities -= {SUPPORT}
        if facts.valid_until is None and UPDATES in policy.restricted_caps:
            capabilities -= {UPDATES}
    return capabilities


def _messages(
    policy: PolicyParams, facts: LicenseFacts, state: State, now: datetime
) -> tuple[str, ...]:
    match state:
        case State.NOTICE if facts.valid_until is not None and (
            _days_left(facts.valid_until, now) <= NOTICE_DIALOG_DAYS
        ):
            return ("notice.banner", "notice.7days")
        case State.NOTICE:
            return ("notice.banner",)
        case State.GRACE:
            return ("grace.banner", "grace.dialog")
        case State.RESTRICTED:
            return ("restricted.banner", "restricted.feature")
        case State.BLOCKED if policy.hard_block_mode == "no_start":
            return ("blocked.no_start",)
        case State.BLOCKED:
            return ("blocked.read_only",)
        case State.REVOKED:
            return ("revoked.dialog",)
        case _:
            return ()


def evaluate(
    policy: PolicyParams,
    license: LicenseFacts | TrialFacts,
    now: datetime,
    last_success_at: datetime | None,
) -> PolicyResult:
    """State, functions and messages at trusted time now; TrialFacts when there is no lease.

    last_success_at is the last successful contact with the server: the current lease expires
    offline_grace_days after it. lease_exp is the exp of a lease issued at now.
    """
    _require_aware(now, last_success_at)
    if isinstance(license, TrialFacts):
        _require_aware(license.first_launch)
        return _trial(license, now)
    _require_aware(license.valid_until, license.support_until)

    state = _state(policy, license, now, last_success_at)
    return PolicyResult(
        state=state,
        capabilities=_capabilities(policy, license, state, now),
        message_ids=_messages(policy, license, state, now),
        lease_exp=(
            None if policy.offline_grace_days is None else now + policy.offline_grace_days * DAY
        ),
        next_check_at=now + timedelta(hours=policy.check_interval_hours),
    )
