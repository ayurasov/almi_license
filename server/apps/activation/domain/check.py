"""ActivationService.check: renewal of the lease (E03-04, E03-07; section 5.3 of document 2)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction

from apps.activation.domain import directives
from apps.activation.domain.fingerprint import within_tolerance
from apps.activation.domain.service import (
    ACTOR,
    ActivationResult,
    components,
    issue_lease,
    load_terms,
)
from apps.activation.models import Activation, ActivationStatus
from apps.audit.domain import record
from apps.licensing.domain import lock_license
from apps.policy.domain import messages_for
from apps.stats.domain import record_usage
from infra.errors import DomainError


@dataclass(frozen=True)
class CheckRequest:
    activation_id: str
    lease_seq: int
    product_version: str
    os: dict[str, Any]
    fingerprint: dict[str, Any] | None
    usage: dict[str, Any] | None
    acked_directives: list[str]
    unsupported_directives: list[str]
    ip: str | None = None


def check(request: CheckRequest, *, now: datetime, issuer: str) -> ActivationResult:
    with transaction.atomic():
        outcome = _check_locked(request, now, issuer)
    if isinstance(outcome, str):
        # The REVOKED lease is committed (its seq is used) before the 403 that carries it.
        raise DomainError("license_revoked", data={"lease": outcome})
    return outcome


def _check_locked(request: CheckRequest, now: datetime, issuer: str) -> ActivationResult | str:
    license_id = (
        Activation.objects.filter(external_id=request.activation_id)
        .values_list("license_id", flat=True)
        .first()
    )
    if license_id is None:
        raise DomainError("activation_not_found")
    license_ = lock_license(license_id)
    activation = Activation.objects.select_for_update().get(external_id=request.activation_id)
    if activation.status not in (ActivationStatus.ACTIVE, ActivationStatus.REVOKED):
        raise DomainError("activation_released")
    terms = load_terms(license_)

    if activation.status == ActivationStatus.REVOKED or license_.status == "revoked":
        token, _ = issue_lease(activation, terms, now, issuer, revoked=True)
        return token

    if request.fingerprint is not None and not within_tolerance(
        components(activation.fp_components), components(request.fingerprint)
    ):
        raise DomainError("rebind_required")

    if request.lease_seq > activation.lease_seq:
        record(
            ACTOR,
            "lease_seq_anomaly",
            "activation",
            activation.external_id,
            at=now,
            ip=request.ip,
            data={"client_seq": request.lease_seq, "server_seq": activation.lease_seq},
        )
        activation.lease_seq = request.lease_seq  # the next lease is max(server, client) + 1

    activation.product_version = request.product_version
    activation.os = request.os
    if request.fingerprint is not None:
        activation.fp_components = request.fingerprint
    activation.last_seen_at = now
    directives.settle(
        activation,
        terms.params,
        request.acked_directives,
        request.unsupported_directives,
        now=now,
        ip=request.ip,
    )
    activation.save()
    if request.usage:
        record_usage(activation.external_id, now, request.usage)

    token, result = issue_lease(activation, terms, now, issuer)
    return ActivationResult(
        created=False,
        activation_id=activation.external_id,
        lease=token,
        policy=result,
        messages=messages_for(result.message_ids, terms.params),
        directives=directives.pending(activation, terms.params),
    )
