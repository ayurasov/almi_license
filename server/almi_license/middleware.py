"""Request metrics for /metrics (E15-05): count, 5xx and duration by route pattern."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from infra import metrics
from infra.clock import monotonic


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
        metrics.REQUESTS.inc(
            (("method", request.method or ""), ("route", route), ("status", status))
        )
        if response.status_code >= 500:
            metrics.ERRORS.inc((("route", route),))
        metrics.DURATION.observe(monotonic() - start, (("route", route),))
        return response
