"""problem+json errors (E05-04, sections 4.5 and 16 of document 2)."""

import json
from typing import Any

import pytest
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from infra.problems import CATALOG, Problem


class Failing(APIView):
    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    error: Exception = Exception()

    def get(self, request: Request) -> Response:
        raise self.error


def call(error: Exception, **headers: str) -> tuple[int, str, dict[str, Any]]:
    class View(Failing):
        pass

    View.error = error
    request = APIRequestFactory().get("/x")
    request.META.update(headers)
    response = View.as_view()(request)
    response.render()
    return response.status_code, response["Content-Type"], json.loads(response.content)


def test_catalog_problem_has_every_field() -> None:
    status, content_type, body = call(
        Problem(
            "seats_exhausted",
            "Использовано 10 из 10 мест.",
            user_message={"ru": "Все места заняты.", "en": "All seats are in use."},
            data={"limit": 10, "used": 10, "reserve": 0},
        ),
        HTTP_X_REQUEST_ID="req-1",
    )

    assert (status, content_type) == (409, "application/problem+json")
    assert body == {
        "type": "https://license.alter-os.ru/problems/seats_exhausted",
        "title": "Нет свободных мест по лицензии",
        "status": 409,
        "code": "seats_exhausted",
        "detail": "Использовано 10 из 10 мест.",
        "request_id": "req-1",
        "user_message": {"ru": "Все места заняты.", "en": "All seats are in use."},
        "data": {"limit": 10, "used": 10, "reserve": 0},
    }


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (exceptions.ValidationError({"key": ["required"]}), "invalid_request"),
        (exceptions.ParseError(), "invalid_request"),
        # Not in the catalog: a 4xx without its own code is answered as invalid_request.
        (exceptions.NotFound(), "invalid_request"),
        (exceptions.MethodNotAllowed("PUT"), "invalid_request"),
        (exceptions.Throttled(), "rate_limited"),
        (exceptions.APIException(), "internal_error"),
    ],
)
def test_framework_errors_map_onto_catalog_codes(error: Exception, code: str) -> None:
    status, _, body = call(error)

    assert body["code"] == code
    assert status == body["status"] == CATALOG[code][0]


def test_request_id_is_generated_when_absent() -> None:
    _, _, first = call(Problem("internal_error"))
    _, _, second = call(Problem("internal_error"))

    assert first["request_id"] and first["request_id"] != second["request_id"]


def test_codes_outside_the_catalog_cannot_be_raised() -> None:
    with pytest.raises(ValueError, match="catalog"):
        Problem("made_up_code")
