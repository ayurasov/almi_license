"""Subscription adapter of AlterOffice Web (E11-01, E11-02; section 11.1 of document 2).

The support app of Nextcloud posts {instanceId, userCount, activeUserCount, apps, version} to
/apps/zammad_organisation_management/api/query/subscription/{key}. The first request of an
instanceId activates a server_instance, later ones run a check with the counters as usage; the
seats follow the general rules (a second instanceId takes a second seat). The request is not
signed (Nextcloud cannot sign), so the key is limited to RATE requests per minute.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from apps.activation.domain import (
    ActivationRequest,
    ActivationResult,
    CheckRequest,
    activate,
    check,
    instance_activation,
)
from apps.api_product.domain.ratelimit import Limit, hit
from apps.catalog.domain import product_info
from apps.compat.domain.ids import server_instance_id
from apps.licensing.domain import (
    InvalidKeyFormat,
    LicenseRecord,
    counts_active_only,
    customer_manager,
    key_hash,
    license_id_by_key_hash,
    license_records,
)
from apps.policy.domain import State
from apps.stats.domain import record_usage
from infra.errors import DomainError

PRODUCT = "alteroffice-web"
RATE = Limit("compat.nextcloud.key", 10, timedelta(minutes=1))
# Dates of the subscription are dates in Moscow time (UTC+3 all year since 2014).
MOSCOW = timezone(timedelta(hours=3))
# A perpetual licence without a support term has no end date; the app needs one.
NO_END = "9999-12-31"
MAX_NAME = 128


class SubscriptionNotFound(Exception):
    """No licence of AlterOffice Web for the key (or it is revoked): 404 as the original service."""


@dataclass(frozen=True)
class SubscriptionRequest:
    key: str
    instance_id: str
    user_count: int | None
    active_user_count: int | None
    apps: Any
    version: str
    ip: str | None = None


def _license(key: str) -> LicenseRecord:
    try:
        license_id = license_id_by_key_hash(key_hash(key))
    except InvalidKeyFormat:
        raise SubscriptionNotFound from None
    if license_id is None:
        raise SubscriptionNotFound
    (license_,) = license_records([license_id])
    if product_info(license_.product_id).code != PRODUCT or license_.status == "revoked":
        raise SubscriptionNotFound
    return license_


def _usage(request: SubscriptionRequest) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    if request.user_count is not None:
        usage["named_users"] = request.user_count
    if request.active_user_count is not None:
        usage["active_users"] = request.active_user_count
    if request.apps:
        usage["apps"] = request.apps
    return usage


def _register(
    request: SubscriptionRequest, license_id: UUID, now: datetime, issuer: str
) -> ActivationResult | None:
    """Activation or check of the instance; None when the server refused it (seats, term)."""
    instance = server_instance_id(request.instance_id)
    existing = instance_activation(license_id, instance)
    try:
        if existing is None:
            result = activate(
                ActivationRequest(
                    license_key=request.key,
                    product_code=PRODUCT,
                    product_version=request.version,
                    edition=None,
                    instance_id=instance,
                    subject_type="server_instance",
                    instance_name=request.instance_id[:MAX_NAME],
                    os={},
                    fingerprint={"scheme": "nextcloud-v1", "components": {}},
                    device_pubkey="",
                    ip=request.ip,
                ),
                now=now,
                issuer=issuer,
            )
            usage = _usage(request)
            if usage:
                record_usage(result.activation_id, now, usage)
            return result
        activation_id, seq = existing
        return check(
            CheckRequest(
                activation_id=activation_id,
                lease_seq=seq,
                product_version=request.version,
                os={},
                fingerprint=None,
                usage=_usage(request) or None,
                acked_directives=[],
                unsupported_directives=[],
                ip=request.ip,
            ),
            now=now,
            issuer=issuer,
        )
    except DomainError as error:
        if error.code == "license_revoked":
            raise SubscriptionNotFound from None
        # The app cannot show a refusal; the subscription is answered, the refusal is in the
        # statistics (no activation) and in the audit (conflicts).
        return None


def _date(moment: datetime) -> str:
    return moment.astimezone(MOSCOW).date().isoformat()


def subscription(
    request: SubscriptionRequest, *, now: datetime, issuer: str, support: dict[str, str]
) -> dict[str, Any]:
    """The answer of the support app: endDate, extendedSupport, amountOfUsers, ..."""
    hit(RATE, request.key, now=now)
    license_ = _license(request.key)
    result = _register(request, license_.id, now, issuer)
    today = now.astimezone(MOSCOW).date()
    end = license_.valid_until or license_.support_until
    limits = license_.limits
    users = limits.get("named_users", limits.get("active_users"))
    if users is None or (result is not None and result.policy.state == State.RESTRICTED):
        # No user limit, or new users are not allowed: the current number is the limit.
        users = request.user_count or 0
    return {
        "endDate": _date(end) if end is not None else NO_END,
        "extendedSupport": license_.support_until is not None
        and license_.support_until.astimezone(MOSCOW).date() >= today,
        "amountOfUsers": users,
        "onlyCountActiveUsers": counts_active_only(limits),
        "accountManagerInfo": customer_manager(license_.customer_id) or dict(support),
    }
