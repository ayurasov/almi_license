"""Request metrics for /metrics (E15-05): count, 5xx and duration by route pattern; headers of
every answer (section 4.3 of document 2)."""

import re
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from infra import metrics
from infra.clock import current_clock, monotonic
from infra.ids import new_ulid

_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class ProtocolHeaders:
    """ALMI-Server-Time on every answer; X-Request-Id: the one of the request (or of the gateway),
    else a new one."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        given = request.META.get("HTTP_X_REQUEST_ID", "")
        if not _REQUEST_ID.fullmatch(given):
            # The same id goes into request_id of a problem+json answer (infra.problems).
            request.META["HTTP_X_REQUEST_ID"] = given = new_ulid(current_clock().now())
        response = self.get_response(request)
        now = current_clock().now()
        response["ALMI-Server-Time"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        response["X-Request-Id"] = given
        return response


class RequestMetrics:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = monotonic()
        response = self.get_response(request)
        match = request.resolver_match
        # The route pattern, not the path: keys and ids never become label values.
        route = match.route if match is not None else "unmatched"
        status = str(response.status_code)
        metrics.REQUESTS.labels(method=request.method or "", route=route, status=status).inc()
        if response.status_code >= 500:
            metrics.ERRORS.labels(route=route).inc()
        metrics.DURATION.labels(route=route).observe(monotonic() - start)
        return response
