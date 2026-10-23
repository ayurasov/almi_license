"""Admin API views: parse, call the domain, shape the response (AGENTS.md, rule 2)."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_admin.api.permissions import ConsoleSession, IsOperator
from apps.api_admin.api.serializers import (
    CustomerPageSerializer,
    CustomerQuerySerializer,
    CustomerSerializer,
    CustomerWriteSerializer,
    SessionRequestSerializer,
    SessionSerializer,
)
from apps.iam.domain import AccountLocked, LoginFailed, account_info, sign_in
from apps.licensing.domain import create_customer, get_customer, list_customers, update_customer
from infra.clock import current_clock
from infra.problems import Problem

WRONG_CREDENTIALS = {"ru": "Неверный логин или пароль.", "en": "Wrong user name or password."}
LOCKED = {
    "ru": "Слишком много неудачных попыток. Повторите вход через 15 минут.",
    "en": "Too many failed attempts. Try again in 15 minutes.",
}


def _valid(serializer: Any) -> dict[str, Any]:
    if not serializer.is_valid():
        fields = {key: [str(m) for m in messages] for key, messages in serializer.errors.items()}
        raise Problem(
            "invalid_request", "request does not match the schema", data={"fields": fields}
        )
    data: dict[str, Any] = serializer.validated_data
    return data


def _actor(request: Request) -> str:
    return f"user:{request.user.get_username()}"


@method_decorator(ensure_csrf_cookie, name="get")
@method_decorator(csrf_protect, name="post")
class SessionView(APIView):
    """Console session: GET who is signed in, POST sign in, DELETE sign out (E07-02)."""

    authentication_classes = [ConsoleSession]
    permission_classes = [AllowAny]

    @extend_schema(responses={200: SessionSerializer}, operation_id="session_get")
    def get(self, request: Request) -> Response:
        account = (
            account_info(request.user) if request.user and request.user.is_authenticated else None
        )
        if account is None:
            raise Problem("signature_invalid", "not signed in")
        return Response(asdict(account))

    @extend_schema(
        request=SessionRequestSerializer,
        responses={200: SessionSerializer},
        operation_id="session_create",
    )
    def post(self, request: Request) -> Response:
        data = _valid(SessionRequestSerializer(data=request.data))
        try:
            user = sign_in(
                data["username"],
                data["password"],
                now=current_clock().now(),
                ip=request.META.get("REMOTE_ADDR"),
            )
        except LoginFailed:
            raise Problem(
                "invalid_request", "sign-in failed", user_message=WRONG_CREDENTIALS
            ) from None
        except AccountLocked as locked:
            raise Problem(
                "rate_limited",
                "account is locked",
                user_message=LOCKED,
                retry_after=locked.retry_after,
            ) from None
        login(request._request, user)
        account = account_info(user)
        return Response(asdict(account) if account else {})

    @extend_schema(responses={204: None}, operation_id="session_delete")
    def delete(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=204)


class CustomersView(APIView):
    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]

    @extend_schema(
        parameters=[CustomerQuerySerializer],
        responses={200: CustomerPageSerializer},
        operation_id="customers_list",
    )
    def get(self, request: Request) -> Response:
        query = _valid(CustomerQuerySerializer(data=request.query_params))
        page = list_customers(**query)
        return Response({"count": page.count, "results": [asdict(c) for c in page.results]})

    @extend_schema(
        request=CustomerWriteSerializer,
        responses={201: CustomerSerializer},
        operation_id="customers_create",
    )
    def post(self, request: Request) -> Response:
        data = _valid(CustomerWriteSerializer(data=request.data))
        customer = create_customer(
            data,
            actor=_actor(request),
            now=current_clock().now(),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return Response(CustomerSerializer(asdict(customer)).data, status=201)


class CustomerView(APIView):
    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]

    @extend_schema(
        parameters=[OpenApiParameter("customer_id", str, OpenApiParameter.PATH)],
        responses={200: CustomerSerializer},
        operation_id="customers_get",
    )
    def get(self, request: Request, customer_id: UUID) -> Response:
        return Response(CustomerSerializer(asdict(get_customer(customer_id))).data)

    @extend_schema(
        parameters=[OpenApiParameter("customer_id", str, OpenApiParameter.PATH)],
        request=CustomerWriteSerializer,
        responses={200: CustomerSerializer},
        operation_id="customers_update",
    )
    def patch(self, request: Request, customer_id: UUID) -> Response:
        data = _valid(CustomerWriteSerializer(data=request.data, partial=True))
        customer = update_customer(
            customer_id,
            data,
            actor=_actor(request),
            now=current_clock().now(),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return Response(CustomerSerializer(asdict(customer)).data)
