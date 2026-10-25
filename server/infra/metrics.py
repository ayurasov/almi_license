"""Prometheus metrics (E15-05) with prometheus-client (question 42).

Under Gunicorn the API has several worker processes: with PROMETHEUS_MULTIPROC_DIR set (the image
entry point does it) every process writes its values to that directory and /metrics adds them up.
Without it (tests, manage.py) the values are those of the process. Labels are bounded by the
caller (route patterns, not paths), so the number of series stays small.
"""

import os
from collections.abc import Iterable

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, multiprocess

REGISTRY = CollectorRegistry(auto_describe=True)

REQUESTS = Counter(
    "almi_http_requests",
    "HTTP requests by method, route and status",
    ["method", "route", "status"],
    registry=REGISTRY,
)
ERRORS = Counter(
    "almi_http_errors", "HTTP responses with status 5xx by route", ["route"], registry=REGISTRY
)
DURATION = Histogram(
    "almi_http_request_duration_seconds",
    "Duration of HTTP requests by route",
    ["route"],
    registry=REGISTRY,
)
WITHOUT_IDEMPOTENCY_KEY = Counter(
    "almi_product_requests_without_idempotency_key",
    "Product API requests that came without Idempotency-Key, by operation (question 37)",
    ["operation"],
    registry=REGISTRY,
)
_ALL = (REQUESTS, ERRORS, DURATION, WITHOUT_IDEMPOTENCY_KEY)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


def gauge(name: str, help_text: str, value: float) -> list[str]:
    """A value computed at scrape time (queue, backup age): the same in every process."""
    return [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {_number(value)}"]


def render(extra: Iterable[str] = ()) -> str:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    else:
        registry = REGISTRY
    text = generate_latest(registry).decode()
    lines = [*extra]
    return text + ("\n".join(lines) + "\n" if lines else "")


def reset() -> None:
    """Tests only: forget the values of this process."""
    for metric in _ALL:
        metric.clear()
