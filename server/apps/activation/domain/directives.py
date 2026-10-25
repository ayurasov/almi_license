"""Directives of an activation (section 8 of document 2, E03-07).

Sent with every response until the product reports them in acked_directives or
unsupported_directives: queued ones (Directive rows) and those of the policy profile
(params["directives"], each with a fixed id).
"""

from datetime import datetime
from typing import Any

from apps.activation.models import Activation, Directive
from apps.audit.domain import record
from infra.ids import new_ulid

ACTOR = "product"


def queue_directive(activation_id: str, type: str, params: dict[str, Any], *, now: datetime) -> str:
    """Queue a directive for the activation; returns its id dir_…."""
    activation = Activation.objects.get(external_id=activation_id)
    directive = Directive.objects.create(
        external_id=f"dir_{new_ulid(now)}",
        activation=activation,
        type=type,
        params=params,
        created_at=now,
    )
    return directive.external_id


def _profile_directives(params: dict[str, Any]) -> list[dict[str, Any]]:
    directives: list[dict[str, Any]] = params.get("directives", [])
    return directives


def settle(
    activation: Activation,
    profile_params: dict[str, Any],
    acked: list[str],
    unsupported: list[str],
    *,
    now: datetime,
    ip: str | None,
) -> None:
    """Mark reported directives; unsupported ones are written to the audit log."""
    queued = Directive.objects.filter(
        activation=activation, acked_at__isnull=True, unsupported_at__isnull=True
    )
    queued.filter(external_id__in=acked).update(acked_at=now)
    for directive in queued.filter(external_id__in=unsupported):
        directive.unsupported_at = now
        directive.save(update_fields=["unsupported_at"])
        _audit_unsupported(activation, directive.external_id, directive.type, now, ip)
    done = set(activation.done_profile_directives)
    for item in _profile_directives(profile_params):
        if item["id"] in done:
            continue
        if item["id"] in unsupported:
            _audit_unsupported(activation, item["id"], item["type"], now, ip)
        if item["id"] in acked or item["id"] in unsupported:
            done.add(item["id"])
    activation.done_profile_directives = sorted(done)


def _audit_unsupported(
    activation: Activation, directive_id: str, kind: str, now: datetime, ip: str | None
) -> None:
    record(
        ACTOR,
        "directive.unsupported",
        "activation",
        activation.external_id,
        at=now,
        ip=ip,
        data={"directive_id": directive_id, "type": kind},
    )


def pending(activation: Activation, profile_params: dict[str, Any]) -> list[dict[str, Any]]:
    """Directives to send: the queue in order of creation, then the profile ones."""
    queued = Directive.objects.filter(
        activation=activation, acked_at__isnull=True, unsupported_at__isnull=True
    ).order_by("created_at", "external_id")
    result = [{"id": d.external_id, "type": d.type, "params": d.params} for d in queued]
    done = set(activation.done_profile_directives)
    result += [
        {"id": item["id"], "type": item["type"]}
        | ({"params": item["params"]} if "params" in item else {})
        for item in _profile_directives(profile_params)
        if item["id"] not in done
    ]
    return result
