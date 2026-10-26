"""ActivationService.activate (E03-01, E03-02, E03-03; section 5.2 of document 2).

One transaction: lock of the license row, checks, seat count, write, lease, audit
(AGENTS.md, rules 6 and 7; section 7.4 of document 1).
"""

import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.activation.domain.fingerprint import within_tolerance
from apps.activation.domain.leases import device_key_thumbprint, lease_claims, sign_lease
from apps.activation.models import Activation, ActivationStatus, Lease
from apps.audit.domain import record
from apps.catalog.domain import (
    capabilities,
    edition_code,
    latest_profile,
    product_id_by_code,
    product_info,
)
from apps.licensing.domain import (
    InvalidKeyFormat,
    LicenseRecord,
    key_facts,
    key_hash,
    lock_license,
    version_supported,
)
from apps.packages.domain import allocated_seats, package_terms
from apps.policy.domain import (
    LicenseFacts,
    PolicyParams,
    PolicyResult,
    accepts_new_activations,
    effective_policy,
    evaluate,
    lease_messages,
    messages_for,
    reserve_pct,
)
from infra.errors import DomainError
from infra.ids import new_ulid

ACTOR = "product"


@dataclass(frozen=True)
class ActivationRequest:
    license_key: str
    product_code: str
    product_version: str
    edition: str | None
    instance_id: UUID
    subject_type: str
    instance_name: str
    os: dict[str, Any]
    fingerprint: dict[str, Any]
    device_pubkey: str
    ip: str | None = None
    offline: bool = False  # by an .alk-req file (section 10 of document 2)


@dataclass(frozen=True)
class ActivationResult:
    created: bool
    activation_id: str
    lease: str
    policy: PolicyResult
    messages: list[dict[str, Any]]
    directives: list[dict[str, Any]]


@dataclass(frozen=True)
class Terms:
    """What a lease of the license is made of: product, edition, functions, policy profile."""

    license: LicenseRecord
    product_code: str
    edition: str | None
    capabilities: frozenset[str]
    policy: PolicyParams
    params: dict[str, Any]
    reserve_pct: int


def _find_license(request: ActivationRequest) -> UUID:
    """The licence of the key; an unknown key, a revoked licence and a key of another product are
    refused after the same two queries, so the time of the answer does not tell which keys exist
    (E16-06). The checks are repeated under the lock of the licence (_terms)."""
    try:
        digest = key_hash(request.license_key)
    except InvalidKeyFormat:
        raise DomainError("invalid_key_format") from None
    wanted = product_id_by_code(request.product_code)
    facts = key_facts(digest)
    if facts is None:
        raise DomainError("key_not_found")
    if facts.status == "revoked":
        raise DomainError("license_revoked")
    if facts.product_id != wanted or (
        request.edition is not None and request.edition != edition_code(facts.edition_id)
    ):
        raise DomainError("product_mismatch")
    return facts.license_id


def load_terms(license_: LicenseRecord, now: datetime) -> Terms:
    product = product_info(license_.product_id)
    profile = latest_profile(license_.policy_profile_code or product.default_profile_code)
    # A lifted block (E01-05) is monitor mode until monitor_until.
    lifted = license_.monitor_until is not None and now < license_.monitor_until
    enforcement = "monitor" if lifted else license_.enforcement
    params = profile.params
    package = package_terms()
    if package is not None and now >= package[0]:
        # An expired package of a local server (section 13.3 of document 2): the licence ends
        # with the package, then the policy of the package for this case applies.
        until, expired = package
        license_ = replace(
            license_,
            valid_until=until if license_.valid_until is None else min(until, license_.valid_until),
        )
        params = params | {k: v for k, v in expired.items() if k in ("expiry_action", "grace_days")}
        enforcement = str(expired.get("enforcement", enforcement)) if not lifted else enforcement
    return Terms(
        license=license_,
        product_code=product.code,
        edition=edition_code(license_.edition_id),
        capabilities=capabilities(license_.product_id, license_.edition_id)
        | frozenset(license_.extra_capabilities),
        policy=effective_policy(params, profile.version, enforcement),
        params=params,
        reserve_pct=reserve_pct(params, license_.reserve_pct),
    )


def _terms(license_: LicenseRecord, request: ActivationRequest, now: datetime) -> Terms:
    """Checks of a new activation in the order of prompt I2-04: revoked, product, term; then the
    version of the product against the licence (422)."""
    if license_.status == "revoked":
        raise DomainError("license_revoked")
    terms = load_terms(license_, now)
    if terms.product_code != request.product_code or (
        request.edition is not None and request.edition != terms.edition
    ):
        raise DomainError("product_mismatch")
    if not accepts_new_activations(terms.policy, license_.valid_until, now):
        raise DomainError("license_expired")
    if not version_supported(request.product_version, license_.max_product_version):
        raise DomainError(
            "unsupported_product_version",
            data={"max_product_version": license_.max_product_version},
        )
    return terms


def components(fingerprint: dict[str, Any]) -> dict[str, str]:
    components: dict[str, str] = fingerprint.get("components", {})
    return components


def _take_seat(terms: Terms) -> bool:
    """in_reserve for the new activation, or seats_exhausted (section 7.4 of document 1).

    Seats handed over to local servers are not available on this server (E09-02).
    """
    limit = terms.license.limit - allocated_seats(terms.license.id)
    reserve = math.ceil(limit * terms.reserve_pct / 100)
    used = Activation.objects.filter(
        license_id=terms.license.id, status=ActivationStatus.ACTIVE
    ).count()
    if used >= limit + reserve:
        raise DomainError(
            "seats_exhausted", data={"used": used, "limit": limit, "reserve": reserve}
        )
    return used >= limit


def issue_lease(
    activation: Activation, terms: Terms, now: datetime, issuer: str, *, revoked: bool = False
) -> tuple[str, PolicyResult]:
    """A new lease with seq = activation.lease_seq + 1; revoked gives the state REVOKED."""
    license_ = terms.license
    status = "revoked" if revoked else license_.status
    if revoked:
        license_ = replace(license_, status=status)
    result = evaluate(
        terms.policy,
        LicenseFacts(
            type=license_.type,
            status=status,
            valid_until=license_.valid_until,
            support_until=license_.support_until,
            capabilities=terms.capabilities,
        ),
        now,
        now,
    )
    package = package_terms()
    if package is not None:
        # A lease of a local server never outlives its package (E09-04).
        until = package[0] if result.lease_exp is None else min(package[0], result.lease_exp)
        result = replace(result, lease_exp=until)
    seq = activation.lease_seq + 1
    claims = lease_claims(
        issuer=issuer,
        activation_id=activation.external_id,
        seq=seq,
        now=now,
        product=product_info(license_.product_id),
        license_=license_,
        edition=terms.edition,
        subject={
            "type": activation.subject_type,
            "instance_id": str(activation.instance_id),
            "fp": activation.fp_components,
            "device_key_thumbprint": device_key_thumbprint(activation.device_pubkey),
        },
        capabilities=terms.capabilities,
        policy=terms.policy,
        result=result,
        messages=lease_messages(terms.params),
    )
    token, digest = sign_lease(claims)
    activation.lease_seq = seq
    activation.save(update_fields=["lease_seq"])
    Lease.objects.update_or_create(
        activation=activation,
        defaults={"seq": seq, "issued_at": now, "exp": result.lease_exp, "jws_hash": digest},
    )
    return token, result


def activate(request: ActivationRequest, *, now: datetime, issuer: str) -> ActivationResult:
    license_id = _find_license(request)
    with transaction.atomic():
        result = _activate_locked(request, license_id, now, issuer)
    if result is None:
        # The conflict row and its audit event are committed before the 409 (E03-06).
        raise DomainError("instance_conflict")
    return result


def _activate_locked(
    request: ActivationRequest, license_id: UUID, now: datetime, issuer: str
) -> ActivationResult | None:
    terms = _terms(lock_license(license_id), request, now)
    existing = Activation.objects.filter(
        license_id=license_id,
        instance_id=request.instance_id,
        status=ActivationStatus.ACTIVE,
    ).first()
    presented = components(request.fingerprint)

    if existing is not None:
        same_key = existing.device_pubkey == request.device_pubkey
        if not same_key and not within_tolerance(components(existing.fp_components), presented):
            _record_conflict(request, existing, license_id, now)
            return None
        existing.device_pubkey = request.device_pubkey
        existing.fp_components = request.fingerprint
        existing.product_version = request.product_version
        existing.os = request.os
        existing.instance_name = request.instance_name
        existing.last_seen_at = now
        existing.offline = request.offline
        existing.save()
        token, result = issue_lease(existing, terms, now, issuer)
        record(
            ACTOR,
            "activation.renewed",
            "activation",
            existing.external_id,
            at=now,
            ip=request.ip,
            data={"key_changed": not same_key},
        )
        return _result(False, existing.external_id, token, result, terms)

    in_reserve = _take_seat(terms)
    activation = Activation.objects.create(
        external_id=f"act_{new_ulid(now)}",
        license_id=license_id,
        instance_id=request.instance_id,
        subject_type=request.subject_type,
        instance_name=request.instance_name,
        fp_components=request.fingerprint,
        device_pubkey=request.device_pubkey,
        in_reserve=in_reserve,
        product_version=request.product_version,
        os=request.os,
        offline=request.offline,
        activated_at=now,
        last_seen_at=now,
        created_at=now,
    )
    token, result = issue_lease(activation, terms, now, issuer)
    record(
        ACTOR,
        "activation.created",
        "activation",
        activation.external_id,
        at=now,
        ip=request.ip,
        data={"license_id": str(license_id), "in_reserve": in_reserve},
    )
    return _result(True, activation.external_id, token, result, terms)


def _result(
    created: bool, activation_id: str, token: str, result: PolicyResult, terms: Terms
) -> ActivationResult:
    return ActivationResult(
        created=created,
        activation_id=activation_id,
        lease=token,
        policy=result,
        messages=messages_for(result.message_ids, terms.params),
        directives=[],
    )


def _record_conflict(
    request: ActivationRequest, existing: Activation, license_id: UUID, now: datetime
) -> None:
    """Clone of an activated instance: keep the evidence for the operator (E03-06)."""
    clone = Activation.objects.create(
        external_id=f"act_{new_ulid(now)}",
        license_id=license_id,
        instance_id=request.instance_id,
        subject_type=request.subject_type,
        instance_name=request.instance_name,
        fp_components=request.fingerprint,
        device_pubkey=request.device_pubkey,
        status=ActivationStatus.CONFLICT,
        product_version=request.product_version,
        os=request.os,
        activated_at=now,
        last_seen_at=now,
        created_at=now,
    )
    record(
        ACTOR,
        "activation.conflict",
        "activation",
        clone.external_id,
        at=now,
        ip=request.ip,
        data={"active": existing.external_id, "instance_id": str(request.instance_id)},
    )
