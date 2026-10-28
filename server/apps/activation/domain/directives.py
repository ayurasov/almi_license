"""Directives of an activation (section 8 of document 2, E03-07).

Sent with every response until the product reports them in acked_directives or
unsupported_directives: queued ones (Directive rows) and those of the policy profile
(params["directives"], each with a fixed id).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.activation.models import Activation, ActivationStatus, Directive
from apps.audit.domain import record
from infra.errors import DomainError
from infra.ids import new_ulid

# Directives an operator may send (section 8 of document 2); collect_diagnostics is stage 2.
TYPES = (
    "refresh_now",
    "update_trust",
    "set_check_interval",
    "show_message",
    "rebind",
    "release",
    "set_server_url",
)
SEVERITIES = ("info", "warning", "critical")
PLACEMENTS = ("banner", "dialog", "about", "tray")
REPEATS = ("once", "daily", "each_start")
MAX_TEXT = 400  # the text of a dialog, rule 3 of document 5


@dataclass(frozen=True)
class DirectiveData:
    id: str
    activation_id: str
    type: str
    params: dict[str, Any]
    created_at: datetime
    state: str  # queued | acked | unsupported
    done_at: datetime | None


ACTOR = "product"


def _invalid(field: str, message: str) -> DomainError:
    return DomainError("invalid_request", field, data={"fields": {field: [message]}})


def directive_params(kind: str, params: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Checked parameters of a directive of the console; unknown keys are dropped."""
    if kind not in TYPES:
        raise _invalid("type", "Недопустимый тип команды.")
    if kind == "set_check_interval":
        hours = params.get("hours")
        if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 720:
            raise _invalid("hours", "Период проверки — от 1 до 720 часов.")
        return {"hours": hours}
    if kind == "set_server_url":
        url = str(params.get("url", "")).strip()
        if not url.startswith("https://") or len(url) > 256 or any(c.isspace() for c in url):
            raise _invalid("url", "Адрес сервера — https://…")
        days = params.get("fallback_days", 14)
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 90:
            raise _invalid("fallback_days", "Срок возврата — от 1 до 90 дней.")
        return {"url": url.rstrip("/"), "fallback_days": days}
    if kind == "show_message":
        message = params.get("message")
        if not isinstance(message, dict):
            raise _invalid("message", "Укажите сообщение.")
        raw = message.get("text")
        text: dict[str, Any] = raw if isinstance(raw, dict) else {}
        ru = str(text.get("ru", "")).strip()
        en = str(text.get("en", "")).strip()
        if not ru or len(ru) > MAX_TEXT or len(en) > MAX_TEXT:
            raise _invalid("text", f"Текст на русском обязателен, до {MAX_TEXT} знаков.")
        severity = message.get("severity", "info")
        placement = message.get("placement", "dialog")
        repeat = message.get("repeat", "once")
        if severity not in SEVERITIES or placement not in PLACEMENTS or repeat not in REPEATS:
            raise _invalid("message", "Недопустимые важность, место или повтор.")
        ident = str(message.get("id") or "").strip()
        return {
            "message": {
                "id": ident[:64] or f"ops.{new_ulid(now).lower()}",
                "severity": severity,
                "placement": placement,
                "repeat": repeat,
                "text": {"ru": ru} | ({"en": en} if en else {}),
            }
        }
    if kind in ("rebind", "release"):
        return {"reason": str(params.get("reason", "")).strip()[:200]}
    return {}


def issue_directive(
    activation_id: str,
    kind: str,
    params: dict[str, Any],
    *,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> DirectiveData:
    """An operator queues a directive; the product gets it with the next check (section 8)."""
    checked = directive_params(kind, params, now)
    activation = Activation.objects.filter(external_id=activation_id).first()
    if activation is None:
        raise DomainError("not_found", "activation not found")
    if activation.status != ActivationStatus.ACTIVE:
        raise _invalid("status", "Команды получает только активная активация.")
    ident = queue_directive(activation_id, kind, checked, now=now)
    record(
        actor,
        "directive.queued",
        "activation",
        activation_id,
        at=now,
        ip=ip,
        data={"directive_id": ident, "type": kind},
    )
    return _data(Directive.objects.select_related("activation").get(external_id=ident))


def issue_license_directive(
    license_id: UUID,
    kind: str,
    params: dict[str, Any],
    *,
    actor: str,
    now: datetime,
    ip: str | None = None,
) -> int:
    """The same directive for every active activation of the licence, e.g. set_server_url when the
    customer moves to a local server (section 8). Returns the number of activations."""
    checked = directive_params(kind, params, now)
    active = list(
        Activation.objects.filter(license_id=license_id, status=ActivationStatus.ACTIVE)
        .order_by("activated_at")
        .values_list("external_id", flat=True)
    )
    for activation_id in active:
        ident = queue_directive(activation_id, kind, checked, now=now)
        record(
            actor,
            "directive.queued",
            "activation",
            activation_id,
            at=now,
            ip=ip,
            data={"directive_id": ident, "type": kind, "license_id": str(license_id)},
        )
    return len(active)


def directives_of(activation_id: str) -> list[DirectiveData]:
    rows = Directive.objects.filter(activation__external_id=activation_id).select_related(
        "activation"
    )
    return [_data(row) for row in rows.order_by("-created_at", "-external_id")]


def _data(row: Directive) -> DirectiveData:
    state = "acked" if row.acked_at else "unsupported" if row.unsupported_at else "queued"
    return DirectiveData(
        id=row.external_id,
        activation_id=row.activation.external_id,
        type=row.type,
        params=dict(row.params),
        created_at=row.created_at,
        state=state,
        done_at=row.acked_at or row.unsupported_at,
    )


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
