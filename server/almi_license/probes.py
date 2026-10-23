"""Liveness and readiness probes for Docker, Nginx and monitoring (outside Product API)."""

import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


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
