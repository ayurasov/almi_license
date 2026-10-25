"""Liveness and readiness probes for Docker, Nginx and monitoring (outside Product API)."""

import logging
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_safe

from apps.outbox.domain import failed_count, queue_size
from infra import metrics
from infra.clock import current_clock

logger = logging.getLogger(__name__)
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"  # prometheus_client.CONTENT_TYPE_LATEST


@require_safe
def health(request: HttpRequest) -> JsonResponse:
    """The process is up; does not touch the database."""
    return JsonResponse({"status": "ok"})


@require_safe
def ready(request: HttpRequest) -> JsonResponse:
    """The server can serve requests: the database connection works."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError as error:
        # The error text may name hosts and users; only its type goes to the log.
        logger.warning("readiness check failed: %s", type(error).__name__)
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _backup_age() -> list[str]:
    """Seconds since the last successful backup (E15-03); -1 when there is none yet."""
    if not settings.BACKUP_STATUS_FILE:
        return []
    try:
        finished = int(Path(settings.BACKUP_STATUS_FILE).read_text(encoding="ascii").strip())
        age = max(int(current_clock().now().timestamp()) - finished, 0)
    except (OSError, ValueError):
        age = -1
    return metrics.gauge("almi_backup_age_seconds", "Seconds since the last backup", age)


@require_safe
def prometheus(request: HttpRequest) -> HttpResponse:
    """Metrics of this process and of the task queue (E15-05); not published by the gateway."""
    extra = [
        *metrics.gauge(
            "almi_task_queue_due", "Due tasks not yet taken", queue_size(now=current_clock().now())
        ),
        *metrics.gauge("almi_task_failed", "Tasks that ran out of attempts", failed_count()),
        *_backup_age(),
    ]
    return HttpResponse(metrics.render(extra), content_type=CONTENT_TYPE)
