"""Views of the compat adapters: parse the old request, call compat.domain, answer the old way.

The products behind these routes cannot change, so the answers keep their original shape
(fixtures in tests/compat) instead of application/problem+json (ADR-008).
"""

import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.api_product.domain.ratelimit import Limited
from apps.compat.domain import SubscriptionNotFound, SubscriptionRequest, subscription
from infra.clock import current_clock

MAX_BODY = 64 * 1024
NOT_FOUND = {"message": "Subscription not found"}
TOO_MANY = {"message": "Too many requests"}
BAD_REQUEST = {"message": "Bad request"}


def _body(request: HttpRequest) -> dict[str, Any] | None:
    if len(request.body) > MAX_BODY:
        return None
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None
    return {key: request.POST.get(key) for key in request.POST}


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@csrf_exempt
@require_POST
def nextcloud_subscription(request: HttpRequest, key: str) -> HttpResponse:
    data = _body(request)
    instance = data.get("instanceId") if data else None
    if data is None or not isinstance(instance, str) or not instance.strip():
        return JsonResponse(BAD_REQUEST, status=400)
    version = data.get("version")
    try:
        answer = subscription(
            SubscriptionRequest(
                key=key,
                instance_id=instance.strip(),
                user_count=_count(data.get("userCount")),
                active_user_count=_count(data.get("activeUserCount")),
                apps=data.get("apps"),
                version=str(version)[:64] if version else "",
                ip=request.META.get("REMOTE_ADDR"),
            ),
            now=current_clock().now(),
            issuer=settings.LEASE_ISSUER,
            support=settings.SUPPORT_CONTACT,
        )
    except SubscriptionNotFound:
        return JsonResponse(NOT_FOUND, status=404)
    except Limited as limited:
        response = JsonResponse(TOO_MANY, status=429)
        response["Retry-After"] = str(limited.retry_after)
        return response
    return JsonResponse(answer)
