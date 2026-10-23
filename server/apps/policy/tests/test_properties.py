"""Properties of PolicyEngine (E04-02): monotonic in time, restrictions only remove functions."""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.policy.domain.engine import (
    LicenseFacts,
    PolicyParams,
    State,
    TrialFacts,
    evaluate,
)

# Severity order of section 8.1 of document 1; TRIAL, UNLICENSED and REVOKED are not on the path.
ORDER = [State.ACTIVE, State.NOTICE, State.GRACE, State.RESTRICTED, State.BLOCKED]
CAPS = ["view", "edit", "save", "create", "export", "print", "updates", "support", "macros"]
START = datetime(2026, 1, 1, tzinfo=UTC)

caps = st.frozensets(st.sampled_from(CAPS))
days = st.integers(min_value=0, max_value=365)
moments = st.integers(min_value=0, max_value=4 * 365 * 86400).map(
    lambda seconds: START + timedelta(seconds=seconds)
)


@st.composite
def policies(draw: st.DrawFn) -> PolicyParams:
    return PolicyParams(
        version=1,
        enforcement=draw(st.sampled_from(["enforce", "monitor"])),
        notify_before_days=draw(days),
        grace_days=draw(days),
        expiry_action=draw(st.sampled_from(["none", "restrict", "block"])),
        # A profile never restricts viewing (section 8.2 of document 1); the engine relies on it.
        restricted_caps=draw(caps) - {"view"},
        restricted_days=draw(st.none() | days),
        hard_block_mode=draw(st.sampled_from(["read_only", "no_start"])),
        read_only_caps=draw(caps) | {"view"},
        offline_grace_days=draw(st.none() | st.integers(min_value=1, max_value=30)),
        check_interval_hours=draw(st.integers(min_value=1, max_value=168)),
        release_after_days=30,
    )


@st.composite
def licenses(draw: st.DrawFn) -> LicenseFacts:
    perpetual = draw(st.booleans())
    return LicenseFacts(
        type="perpetual" if perpetual else "subscription",
        status=draw(st.sampled_from(["active", "suspended"])),
        valid_until=None if perpetual else draw(moments),
        support_until=draw(st.none() | moments),
        capabilities=draw(caps) | {"view"},
    )


def rank(state: State) -> int:
    return ORDER.index(state)


@settings(max_examples=500)
@given(policy=policies(), license_=licenses(), first=moments, second=moments)
def test_state_never_improves_as_time_goes_on(
    policy: PolicyParams, license_: LicenseFacts, first: datetime, second: datetime
) -> None:
    earlier, later = sorted([first, second])
    # A product that has been online all along: last contact is the current moment.
    before = evaluate(policy, license_, earlier, earlier)
    after = evaluate(policy, license_, later, later)

    assert rank(after.state) >= rank(before.state)


@settings(max_examples=500)
@given(policy=policies(), license_=licenses(), now=moments, offline=days)
def test_losing_contact_never_improves_the_state(
    policy: PolicyParams, license_: LicenseFacts, now: datetime, offline: int
) -> None:
    online = evaluate(policy, license_, now, now)
    stale = evaluate(policy, license_, now, now - timedelta(days=offline))

    assert rank(stale.state) >= rank(online.state)


@settings(max_examples=500)
@given(policy=policies(), license_=licenses(), now=moments)
def test_restricted_capabilities_are_a_subset_of_active(
    policy: PolicyParams, license_: LicenseFacts, now: datetime
) -> None:
    result = evaluate(policy, license_, now, now)

    assert result.capabilities <= license_.capabilities | policy.read_only_caps
    if result.state == State.RESTRICTED:
        assert result.capabilities <= license_.capabilities
        if policy.enforcement == "enforce":
            assert not result.capabilities & policy.restricted_caps


@settings(max_examples=500)
@given(policy=policies(), license_=licenses(), now=moments)
def test_view_is_always_available_unless_start_is_forbidden(
    policy: PolicyParams, license_: LicenseFacts, now: datetime
) -> None:
    result = evaluate(policy, license_, now, now)

    no_start = (
        result.state in (State.BLOCKED, State.REVOKED)
        and policy.enforcement == "enforce"
        and policy.hard_block_mode == "no_start"
    )
    assert ("view" in result.capabilities) != no_start


@given(policy=policies(), license_=licenses(), now=moments)
def test_revoked_wins_over_dates(
    policy: PolicyParams, license_: LicenseFacts, now: datetime
) -> None:
    revoked = LicenseFacts(
        type=license_.type,
        status="revoked",
        valid_until=license_.valid_until,
        support_until=license_.support_until,
        capabilities=license_.capabilities,
    )
    assert evaluate(policy, revoked, now, now).state == State.REVOKED


@given(policy=policies(), license_=licenses(), now=moments)
def test_lease_exp_and_next_check(
    policy: PolicyParams, license_: LicenseFacts, now: datetime
) -> None:
    result = evaluate(policy, license_, now, now)

    if policy.offline_grace_days is None:
        assert result.lease_exp is None
    else:
        assert result.lease_exp == now + timedelta(days=policy.offline_grace_days)
    assert result.next_check_at == now + timedelta(hours=policy.check_interval_hours)


def test_naive_datetimes_are_refused() -> None:
    policy = PolicyParams.from_json(
        {
            "version": 1,
            "enforcement": "enforce",
            "notify_before_days": 30,
            "grace_days": 14,
            "expiry_action": "restrict",
            "restricted_caps": [],
            "restricted_days": None,
            "hard_block_mode": "read_only",
            "read_only_caps": ["view"],
            "offline_grace_days": None,
            "check_interval_hours": 24,
            "release_after_days": 30,
        }
    )
    trial = TrialFacts(first_launch=None, product_capabilities=frozenset({"view"}))

    with pytest.raises(ValueError, match="timezone"):
        evaluate(policy, trial, datetime(2027, 1, 1), None)  # noqa: DTZ001
