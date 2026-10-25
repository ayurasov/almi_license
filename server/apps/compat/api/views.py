"""Views of the compat adapters: parse the old request, call compat.domain, answer the old way.

The products behind these routes cannot change, so the answers keep their original shape
(fixtures in tests/compat) instead of application/problem+json (ADR-008).
"""

import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.api_product.domain.ratelimit import Limited
from apps.compat.domain import (
    LegacyResult,
    SubscriptionNotFound,
    SubscriptionRequest,
    legacy_activate,
    subscription,
)
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


# Status codes of /api/activate/ by outcome; fixed by the fixtures of E00-09 (tests/compat).
LEGACY_STATUS = {
    "activated": 200,
    "already_activated": 200,
    "bad_request": 400,
    "not_found": 404,
    "expired": 403,
    "no_seats": 409,
    "too_many": 429,
}
LEGACY_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Активация лицензии</title></head>
<body>
<h1>Активация лицензии</h1>
<p class="result">{text}</p>{usage}
</body>
</html>
"""


def _wants_json(request: HttpRequest, params: dict[str, str]) -> bool:
    return params.get("format") == "json" or "application/json" in request.headers.get("Accept", "")


def _legacy_response(
    request: HttpRequest, params: dict[str, str], result: LegacyResult
) -> HttpResponse:
    status = LEGACY_STATUS[result.outcome]
    response: HttpResponse
    if _wants_json(request, params):
        body: dict[str, Any] = {"success": result.ok, "message": result.text}
        if result.total is not None:
            body |= {"used": result.used, "total": result.total}
        response = JsonResponse(body, status=status, json_dumps_params={"ensure_ascii": False})
    else:
        usage = ""
        if result.total is not None:
            usage = f'\n<p class="usage">Использовано: {result.used} из {result.total}</p>'
        page = LEGACY_PAGE.format(text=escape(result.text), usage=usage)
        response = HttpResponse(page, status=status, content_type="text/html; charset=utf-8")
    if result.retry_after is not None:
        response["Retry-After"] = str(result.retry_after)
    return response


@csrf_exempt
@require_http_methods(["GET", "POST"])
def legacy_activate_view(request: HttpRequest) -> HttpResponse:
    """GET or POST /api/activate/?data=&host=&lic=[&format=json] of registration.sh."""
    source = request.POST if request.method == "POST" and request.POST else request.GET
    params = {key: str(source.get(key, "")).strip() for key in ("data", "host", "lic", "format")}
    result = legacy_activate(
        params["data"],
        params["host"],
        params["lic"],
        ip=request.META.get("REMOTE_ADDR", ""),
        now=current_clock().now(),
        issuer=settings.LEASE_ISSUER,
    )
    return _legacy_response(request, params, result)
