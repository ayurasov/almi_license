"""Access to the Admin API: a console session (E07-02) of an operator or administrator."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.iam.domain import OPERATOR_ROLES, account_info


class ConsoleSession(SessionAuthentication):
    """Session cookie with CSRF; a 401 names the scheme so the console can redirect to sign-in."""

    def authenticate_header(self, request: Request) -> str:
        return "Session"


class IsOperator(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if user is None or not user.is_authenticated:
            return False
        account = account_info(user)
        return account is not None and account.role in OPERATOR_ROLES


class ConsoleSessionScheme(OpenApiAuthenticationExtension):
    """Describes the console session cookie in the Admin API schema."""

    target_class = "apps.api_admin.api.permissions.ConsoleSession"
    name = "consoleSession"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}
