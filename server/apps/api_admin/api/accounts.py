"""Admin API: console users, for an ALMI administrator only (E07-09)."""

from dataclasses import asdict
from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import actor_of, valid
from apps.api_admin.api.permissions import ConsoleSession, IsAdmin
from apps.iam.domain import add_account, change_account, list_accounts, reset_password
from infra.clock import current_clock

USERNAME = OpenApiParameter("username", str, OpenApiParameter.PATH)


class _Admin(APIView):
    authentication_classes = [ConsoleSession]
    permission_classes = [IsAdmin]

    def context(self, request: Request) -> dict[str, Any]:
        return {
            "actor": actor_of(request),
            "now": current_clock().now(),
            "ip": request.META.get("REMOTE_ADDR"),
        }


class AccountsView(_Admin):
    @extend_schema(responses={200: s.AccountSerializer(many=True)}, operation_id="accounts_list")
    def get(self, request: Request) -> Response:
        return Response([s.AccountSerializer(asdict(a)).data for a in list_accounts()])

    @extend_schema(
        request=s.AccountCreateSerializer,
        responses={201: s.IssuedPasswordSerializer},
        operation_id="accounts_create",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.AccountCreateSerializer(data=request.data))
        issued = add_account(
            data["username"],
            data["role"],
            customer_id=data.get("customer_id"),
            **self.context(request),
        )
        return Response(s.IssuedPasswordSerializer(asdict(issued)).data, status=201)


class AccountView(_Admin):
    @extend_schema(
        parameters=[USERNAME],
        request=s.AccountUpdateSerializer,
        responses={200: s.AccountSerializer},
        operation_id="accounts_update",
    )
    def patch(self, request: Request, username: str) -> Response:
        data = valid(s.AccountUpdateSerializer(data=request.data, partial=True))
        account = change_account(username, **data, **self.context(request))
        return Response(s.AccountSerializer(asdict(account)).data)


class AccountPasswordView(_Admin):
    @extend_schema(
        parameters=[USERNAME],
        request=None,
        responses={200: s.IssuedPasswordSerializer},
        operation_id="accounts_reset_password",
    )
    def post(self, request: Request, username: str) -> Response:
        issued = reset_password(username, **self.context(request))
        return Response(s.IssuedPasswordSerializer(asdict(issued)).data)
