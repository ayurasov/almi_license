"""API errors as RFC 9457 application/problem+json (E05-04, section 4.5 of document 2).

Only codes of the catalog of section 16 of document 2 exist (AGENTS.md, rule 10).
"""

import uuid
from datetime import datetime
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response

PROBLEM_TYPE = "https://license.alter-os.ru/problems/"
CONTENT_TYPE = "application/problem+json"

# code -> (HTTP status, title); section 16 of document 2
CATALOG: dict[str, tuple[int, str]] = {
    "invalid_request": (400, "Нарушен формат запроса"),
    "invalid_key_format": (400, "Неверный формат ключа"),
    "signature_invalid": (401, "Подпись запроса неверна"),
    "clock_skew": (401, "Отклонение времени"),
    "license_revoked": (403, "Лицензия отозвана"),
    "license_expired": (403, "Срок лицензии истёк"),
    "product_mismatch": (403, "Ключ другого продукта"),
    "key_not_found": (404, "Ключ не найден"),
    "activation_not_found": (404, "Активация не найдена"),
    "seats_exhausted": (409, "Нет свободных мест по лицензии"),
    "instance_conflict": (409, "Конфликт экземпляра"),
    "idempotency_conflict": (409, "Ключ идемпотентности использован с другим телом"),
    "activation_released": (410, "Место освобождено"),
    "rebind_required": (412, "Отпечаток вне допуска"),
    "payload_too_large": (413, "Слишком большое тело запроса"),
    "unsupported_product_version": (422, "Версия продукта не поддерживается лицензией"),
    "upgrade_required": (426, "Протокол устарел"),
    "rate_limited": (429, "Слишком много запросов"),
    "internal_error": (500, "Ошибка сервера"),
    "maintenance": (503, "Обслуживание"),
}

# Errors raised by DRF itself are mapped by status onto the closest catalog code.
_BY_STATUS = {
    status.HTTP_401_UNAUTHORIZED: "signature_invalid",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


class Problem(exceptions.APIException):
    """An error of the catalog; detail is for logs and operators, user_message for the user."""

    def __init__(
        self,
        code: str,
        detail: str | None = None,
        *,
        user_message: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        server_time: datetime | None = None,
    ) -> None:
        if code not in CATALOG:
            raise ValueError(f"{code!r} is not in the error catalog (document 2, section 16)")
        self.status_code, title = CATALOG[code]
        super().__init__(detail or title, code)
        self.problem_code = code
        self.title = title
        self.user_message = user_message
        self.data = data
        self.server_time = server_time


def _problem_of(exc: exceptions.APIException) -> Problem:
    if isinstance(exc, Problem):
        return exc
    if exc.status_code >= 500:
        return Problem("internal_error")
    return Problem(_BY_STATUS.get(exc.status_code, "invalid_request"))


def problem_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF EXCEPTION_HANDLER: every APIException becomes problem+json; others propagate (500)."""
    if not isinstance(exc, exceptions.APIException):
        return None
    problem = _problem_of(exc)
    request = context.get("request")
    request_id = (request.META.get("HTTP_X_REQUEST_ID") if request is not None else None) or (
        uuid.uuid4().hex
    )
    body: dict[str, Any] = {
        "type": PROBLEM_TYPE + problem.problem_code,
        "title": problem.title,
        "status": problem.status_code,
        "code": problem.problem_code,
        "detail": str(problem.detail),
        "request_id": request_id,
    }
    if problem.user_message is not None:
        body["user_message"] = problem.user_message
    if problem.data is not None:
        body["data"] = problem.data
    if problem.server_time is not None:
        body["server_time"] = problem.server_time.isoformat().replace("+00:00", "Z")
    response = Response(body, status=problem.status_code, content_type=CONTENT_TYPE)
    view = context.get("view")
    if problem.status_code == status.HTTP_401_UNAUTHORIZED and view is not None:
        # RFC 9110, 15.5.2: a 401 names the authentication scheme.
        authenticate_header = view.get_authenticate_header(request)
        if authenticate_header:
            response["WWW-Authenticate"] = authenticate_header
    return response
