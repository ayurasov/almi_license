"""ActivationService.activate (E03-01, E03-02, E03-03; section 5.2 of document 2).

One transaction: lock of the license row, checks, seat count, write, lease, audit
(AGENTS.md, rules 6 and 7; section 7.4 of document 1).
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.activation.domain.fingerprint import within_tolerance
from apps.activation.domain.leases import device_key_thumbprint, lease_claims, sign_lease
from apps.activation.models import Activation, ActivationStatus, Lease
from apps.audit.domain import record
from apps.catalog.domain import capabilities, edition_code, latest_profile, product_info
from apps.licensing.domain import (
    InvalidKeyFormat,
    LicenseRecord,
    key_hash,
    license_id_by_key_hash,
    lock_license,
)
from apps.policy.domain import (
    LicenseFacts,
    PolicyParams,
    PolicyResult,
    accepts_new_activations,
    effective_policy,
    evaluate,
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


@dataclass(frozen=True)
class ActivationResult:
    created: bool
    activation_id: str
    lease: str
    policy: PolicyResult


@dataclass(frozen=True)
class _Terms:
    license: LicenseRecord
    product_code: str
    edition: str | None
    capabilities: frozenset[str]
    policy: PolicyParams
    reserve_pct: int


def _find_license(raw_key: str) -> UUID:
    try:
        digest = key_hash(raw_key)
    except InvalidKeyFormat:
        raise DomainError("invalid_key_format") from None
    license_id = license_id_by_key_hash(digest)
    if license_id is None:
        raise DomainError("key_not_found")
    return license_id


def _terms(license_: LicenseRecord, request: ActivationRequest, now: datetime) -> _Terms:
    if license_.status == "revoked":
        raise DomainError("license_revoked")
    product = product_info(license_.product_id)
    edition = edition_code(license_.edition_id)
    if product.code != request.product_code or (
        request.edition is not None and request.edition != edition
    ):
        raise DomainError("product_mismatch")
    profile = latest_profile(license_.policy_profile_code or product.default_profile_code)
    policy = effective_policy(profile.params, profile.version, license_.enforcement)
    if not accepts_new_activations(policy, license_.valid_until, now):
        raise DomainError("license_expired")
    return _Terms(
        license=license_,
        product_code=product.code,
        edition=edition,
        capabilities=capabilities(license_.product_id, license_.edition_id)
        | frozenset(license_.extra_capabilities),
        policy=policy,
        reserve_pct=reserve_pct(profile.params, license_.reserve_pct),
    )


def _components(fingerprint: dict[str, Any]) -> dict[str, str]:
    components: dict[str, str] = fingerprint.get("components", {})
    return components


def _take_seat(terms: _Terms) -> bool:
    """in_reserve for the new activation, or seats_exhausted (section 7.4 of document 1)."""
    limit = terms.license.limit
    reserve = math.ceil(limit * terms.reserve_pct / 100)
    used = Activation.objects.filter(
        license_id=terms.license.id, status=ActivationStatus.ACTIVE
    ).count()
    if used >= limit + reserve:
        raise DomainError(
            "seats_exhausted", data={"used": used, "limit": limit, "reserve": reserve}
        )
    return used >= limit


def _issue(
    activation: Activation, terms: _Terms, now: datetime, issuer: str
) -> tuple[str, PolicyResult]:
    license_ = terms.license
    result = evaluate(
        terms.policy,
        LicenseFacts(
            type=license_.type,
            status=license_.status,
            valid_until=license_.valid_until,
            support_until=license_.support_until,
            capabilities=terms.capabilities,
        ),
        now,
        now,
    )
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
    license_id = _find_license(request.license_key)
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
    presented = _components(request.fingerprint)

    if existing is not None:
        same_key = existing.device_pubkey == request.device_pubkey
        if not same_key and not within_tolerance(_components(existing.fp_components), presented):
            _record_conflict(request, existing, license_id, now)
            return None
        existing.device_pubkey = request.device_pubkey
        existing.fp_components = request.fingerprint
        existing.product_version = request.product_version
        existing.os = request.os
        existing.instance_name = request.instance_name
        existing.last_seen_at = now
        existing.save()
        token, result = _issue(existing, terms, now, issuer)
        record(
            ACTOR,
            "activation.renewed",
            "activation",
            existing.external_id,
            at=now,
            ip=request.ip,
            data={"key_changed": not same_key},
        )
        return ActivationResult(False, existing.external_id, token, result)

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
        activated_at=now,
        last_seen_at=now,
        created_at=now,
    )
    token, result = _issue(activation, terms, now, issuer)
    record(
        ACTOR,
        "activation.created",
        "activation",
        activation.external_id,
        at=now,
        ip=request.ip,
        data={"license_id": str(license_id), "in_reserve": in_reserve},
    )
    return ActivationResult(True, activation.external_id, token, result)


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
