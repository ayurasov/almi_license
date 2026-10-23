"""Helpers of Admin API views: request validation and the audit actor."""

from typing import Any

from rest_framework.request import Request

from infra.problems import Problem


def valid(serializer: Any) -> dict[str, Any]:
    if not serializer.is_valid():
        fields = {key: [str(m) for m in messages] for key, messages in serializer.errors.items()}
        raise Problem(
            "invalid_request", "request does not match the schema", data={"fields": fields}
        )
    data: dict[str, Any] = serializer.validated_data
    return data


def actor_of(request: Request) -> str:
    return f"user:{request.user.get_username()}"
