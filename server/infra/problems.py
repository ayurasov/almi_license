"""API errors as RFC 9457 application/problem+json (E05-04, section 4.5 of document 2).

Only codes of the catalog of section 16 of document 2 exist (AGENTS.md, rule 10).
"""

import uuid
from datetime import datetime
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response

from infra.errors import DomainError

PROBLEM_TYPE = "https://license.alter-os.ru/problems/"
CONTENT_TYPE = "application/problem+json"

# code -> (HTTP status, title); section 16 of document 2
CATALOG: dict[str, tuple[int, str]] = {
    "invalid_request": (400, "Нарушен формат запроса"),
    "invalid_key_format": (400, "Неверный формат ключа"),
    "captcha_required": (400, "Нужна капча"),
    "validation_failed": (400, "Ошибка в полях запроса"),
    "not_authenticated": (401, "Нужен вход в консоль"),
    "forbidden": (403, "Недостаточно прав"),
    "not_found": (404, "Объект не найден"),
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

# Texts shown to the user (section 5 of document 5); {used}, {limit} come from data.
USER_MESSAGES: dict[str, dict[str, str]] = {
    "captcha_required": {
        "ru": "Введите символы с картинки.",
        "en": "Enter the characters from the picture.",
    },
    "forbidden": {
        "ru": "Недостаточно прав для этого действия.",
        "en": "You do not have permission for this action.",
    },
    "not_found": {
        "ru": "Объект не найден или недоступен.",
        "en": "The object was not found or is not available.",
    },
    "invalid_key_format": {
        "ru": "Ключ введён неверно. Проверьте его и попробуйте снова.",
        "en": "The key is incorrect. Check it and try again.",
    },
    "key_not_found": {
        "ru": "Ключ не найден. Проверьте ключ или обратитесь к поставщику лицензии.",
        "en": "The key was not found. Check it or contact your license supplier.",
    },
    "license_expired": {
        "ru": "Срок действия этой лицензии истёк. Обратитесь к администратору для продления.",
        "en": "This license has expired. Contact your administrator to renew it.",
    },
    "license_revoked": {
        "ru": "Лицензия отозвана. Обратитесь к администратору.",
        "en": "The license has been revoked. Contact your administrator.",
    },
    "product_mismatch": {
        "ru": "Этот ключ предназначен для другого продукта или редакции.",
        "en": "This key is for a different product or edition.",
    },
    "seats_exhausted": {
        "ru": "Все лицензии по этому ключу уже используются ({used} из {limit}). Освободите "
        "лицензию на другом компьютере или обратитесь к администратору.",
        "en": "All licenses for this key are in use ({used} of {limit}). Release a license on "
        "another computer or contact your administrator.",
    },
    "instance_conflict": {
        "ru": "Этот компьютер похож на копию уже активированного. Нажмите «Активировать заново», "
        "чтобы зарегистрировать его как новый.",
        "en": 'This computer looks like a copy of an already activated one. Click "Activate '
        'again" to register it as a new computer.',
    },
}

# Errors raised by DRF itself are mapped by status onto the closest catalog code.
_BY_STATUS = {
    status.HTTP_401_UNAUTHORIZED: "signature_invalid",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}
# The Admin API (console) has its own codes for a session, rights, objects and fields
# (section 16 of document 2, question 23); the Product and Sync APIs keep theirs.
ADMIN_PREFIX = "/api/admin/"
_ADMIN_BY_STATUS = _BY_STATUS | {
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
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
        retry_after: int | None = None,
    ) -> None:
        if code not in CATALOG:
            raise ValueError(f"{code!r} is not in the error catalog (document 2, section 16)")
        self.status_code, title = CATALOG[code]
        super().__init__(detail or title, code)
        self.problem_code = code
        self.title = title
        if user_message is None and code in USER_MESSAGES:
            values = data or {}
            user_message = {
                lang: text.format(**values) if "{" in text else text
                for lang, text in USER_MESSAGES[code].items()
            }
        self.user_message = user_message
        self.data = data
        self.server_time = server_time
        self.retry_after = retry_after


def _problem_of(exc: exceptions.APIException | DomainError, *, admin: bool) -> Problem:
    if isinstance(exc, DomainError):
        problem = Problem(exc.code, exc.detail or None, data=exc.data)
    elif isinstance(exc, Problem):
        problem = exc
    elif exc.status_code >= 500:
        return Problem("internal_error")
    else:
        detail = exc.detail if isinstance(exc.detail, str) else None
        by_status = _ADMIN_BY_STATUS if admin else _BY_STATUS
        return Problem(by_status.get(exc.status_code, "invalid_request"), detail)
    if admin and problem.problem_code == "invalid_request" and "fields" in (problem.data or {}):
        # Errors of the fields of a console form.
        return Problem(
            "validation_failed",
            str(problem.detail),
            user_message=problem.user_message,
            data=problem.data,
        )
    return problem


def problem_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF EXCEPTION_HANDLER: every APIException becomes problem+json; others propagate (500)."""
    if not isinstance(exc, exceptions.APIException | DomainError):
        return None
    request = context.get("request")
    admin = request is not None and request.path.startswith(ADMIN_PREFIX)
    problem = _problem_of(exc, admin=admin)
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
    if problem.retry_after is not None:
        response["Retry-After"] = str(problem.retry_after)
    view = context.get("view")
    if problem.status_code == status.HTTP_401_UNAUTHORIZED and view is not None:
        # RFC 9110, 15.5.2: a 401 names the authentication scheme.
        authenticate_header = view.get_authenticate_header(request)
        if authenticate_header:
            response["WWW-Authenticate"] = authenticate_header
    return response
