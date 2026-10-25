"""Hourly recalculation of licence states (E12-03).

The state the products would get now is computed by PolicyEngine from the terms of each licence
(profile, enforcement, lifted block, package of a local server) and kept on the licence for the
console and statistics. It is not a change of rights: no audit event, no new rights_version.
"""

from datetime import datetime
from uuid import UUID

from apps.activation.domain.service import load_terms
from apps.licensing.domain import license_ids, license_records, save_states
from apps.policy.domain import LicenseFacts, State, evaluate

TASK_KIND = "licensing.recompute_states"


def recompute_states(*, now: datetime) -> int:
    count = 0
    for batch in license_ids():
        states: dict[UUID, str] = {}
        for license_ in license_records(batch):
            if license_.status == "revoked":
                states[license_.id] = State.REVOKED.value
                continue
            terms = load_terms(license_, now)
            lic = terms.license
            result = evaluate(
                terms.policy,
                LicenseFacts(
                    type=lic.type,
                    status=lic.status,
                    valid_until=lic.valid_until,
                    support_until=lic.support_until,
                    capabilities=terms.capabilities,
                ),
                now,
                now,
            )
            states[license_.id] = result.state.value
        save_states(states, at=now)
        count += len(states)
    return count


def run_recompute_task(payload: dict[str, object], now: datetime) -> None:
    """Handler of TASK_KIND in the outbox queue."""
    recompute_states(now=now)
