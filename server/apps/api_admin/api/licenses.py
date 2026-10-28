"""Admin API: licenses, keys, activations, products (E01-05…E01-08, E07-04, E07-05)."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activation.domain import (
    directives_of,
    issue_directive,
    issue_license_directive,
    license_usage,
    list_activations,
    release_by_operator,
)
from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import actor_of, valid
from apps.api_admin.api.permissions import CanRead, ConsoleSession, IsOperator
from apps.audit.domain import events_for
from apps.catalog.domain import list_products
from apps.iam.domain import viewer_customer
from apps.licensing.domain import (
    create_license,
    get_license,
    issue_key,
    lift_block,
    list_licenses,
    renew_license,
    set_license_status,
    transfer_license,
    update_settings,
)
from apps.packages.domain import license_allocated
from infra.clock import current_clock
from infra.problems import Problem

LICENSE_ID = OpenApiParameter("license_id", str, OpenApiParameter.PATH)
ACTIVATION_ID = OpenApiParameter("activation_id", str, OpenApiParameter.PATH)


class _Operator(APIView):
    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]

    def context(self, request: Request) -> dict[str, Any]:
        return {
            "actor": actor_of(request),
            "now": current_clock().now(),
            "ip": request.META.get("REMOTE_ADDR"),
        }


class _Reader(_Operator):
    """Read access for operators and customer viewers (E07-08)."""

    permission_classes = [CanRead]

    def scope(self, request: Request) -> UUID | None:
        """The customer of a customer viewer; None for ALMI staff."""
        return viewer_customer(request.user)


def _license(data: Any) -> dict[str, Any]:
    return dict(s.LicenseSerializer(asdict(data)).data)


class LicensesView(_Reader):
    @extend_schema(
        parameters=[s.LicenseQuerySerializer],
        responses={200: s.LicensePageSerializer},
        operation_id="licenses_list",
    )
    def get(self, request: Request) -> Response:
        query = valid(s.LicenseQuerySerializer(data=request.query_params))
        scope = self.scope(request)
        if scope is not None:
            query["customer_id"] = scope
        page = list_licenses(**query)
        return Response({"count": page.count, "results": [_license(item) for item in page.results]})

    @extend_schema(
        request=s.LicenseCreateSerializer,
        responses={201: s.LicenseSerializer},
        operation_id="licenses_create",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.LicenseCreateSerializer(data=request.data))
        return Response(_license(create_license(data, **self.context(request))), status=201)


class LicenseView(_Reader):
    @extend_schema(
        parameters=[LICENSE_ID], responses={200: s.LicenseSerializer}, operation_id="licenses_get"
    )
    def get(self, request: Request, license_id: UUID) -> Response:
        return Response(_license(get_license(license_id, customer_id=self.scope(request))))


class LicenseRenewView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=s.RenewSerializer,
        responses={200: s.LicenseSerializer},
        operation_id="licenses_renew",
    )
    def post(self, request: Request, license_id: UUID) -> Response:
        data = valid(s.RenewSerializer(data=request.data))
        result = renew_license(
            license_id,
            valid_until=data["valid_until"],
            support_until=data.get("support_until"),
            limit=data.get("limit"),
            **self.context(request),
        )
        return Response(_license(result))


def _status_view(status: str, operation: str) -> type[_Operator]:
    class StatusView(_Operator):
        @extend_schema(
            parameters=[LICENSE_ID],
            request=s.ReasonSerializer,
            responses={200: s.LicenseSerializer},
            operation_id=operation,
        )
        def post(self, request: Request, license_id: UUID) -> Response:
            data = valid(s.ReasonSerializer(data=request.data))
            result = set_license_status(
                license_id, status, reason=data["reason"], **self.context(request)
            )
            return Response(_license(result))

    StatusView.__name__ = f"License{operation.title().replace('_', '')}View"
    return StatusView


LicenseSuspendView = _status_view("suspended", "licenses_suspend")
LicenseResumeView = _status_view("active", "licenses_resume")
LicenseRevokeView = _status_view("revoked", "licenses_revoke")


class LicenseLiftBlockView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=s.LiftBlockSerializer,
        responses={200: s.LicenseSerializer},
        operation_id="licenses_lift_block",
    )
    def post(self, request: Request, license_id: UUID) -> Response:
        data = valid(s.LiftBlockSerializer(data=request.data))
        result = lift_block(
            license_id, until=data["until"], reason=data["reason"], **self.context(request)
        )
        return Response(_license(result))


class LicenseSettingsView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=s.SettingsSerializer,
        responses={200: s.LicenseSerializer},
        operation_id="licenses_settings",
    )
    def patch(self, request: Request, license_id: UUID) -> Response:
        data = valid(s.SettingsSerializer(data=request.data, partial=True))
        return Response(_license(update_settings(license_id, data, **self.context(request))))


class LicenseTransferView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=s.TransferSerializer,
        responses={200: s.LicenseSerializer},
        operation_id="licenses_transfer",
    )
    def post(self, request: Request, license_id: UUID) -> Response:
        data = valid(s.TransferSerializer(data=request.data))
        result = transfer_license(
            license_id,
            data["customer_id"],
            reason=data["reason"],
            document=data["document"],
            allocated=license_allocated,
            **self.context(request),
        )
        return Response(_license(result))


class LicenseKeysView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=None,
        responses={201: s.IssuedKeySerializer},
        operation_id="licenses_issue_key",
    )
    def post(self, request: Request, license_id: UUID) -> Response:
        issued = issue_key(license_id, **self.context(request))
        return Response(
            {"license_id": issued.license_id, "key": issued.key, "key_mask": issued.key_mask},
            status=201,
        )


class LicenseUsageView(_Reader):
    @extend_schema(
        parameters=[LICENSE_ID], responses={200: s.UsageSerializer}, operation_id="licenses_usage"
    )
    def get(self, request: Request, license_id: UUID) -> Response:
        get_license(license_id, customer_id=self.scope(request))
        return Response(s.UsageSerializer(asdict(license_usage(license_id))).data)


class LicenseHistoryView(_Reader):
    @extend_schema(
        parameters=[LICENSE_ID],
        responses={200: s.HistoryEventSerializer(many=True)},
        operation_id="licenses_history",
    )
    def get(self, request: Request, license_id: UUID) -> Response:
        get_license(license_id, customer_id=self.scope(request))
        events = events_for("license", str(license_id))
        return Response([s.HistoryEventSerializer(event).data for event in events])


class ActivationsView(_Reader):
    @extend_schema(
        parameters=[s.ActivationQuerySerializer],
        responses={200: s.ActivationPageSerializer},
        operation_id="activations_list",
    )
    def get(self, request: Request) -> Response:
        query = valid(s.ActivationQuerySerializer(data=request.query_params))
        scope = self.scope(request)
        if scope is not None:
            # A customer viewer sees the activations of one of its licences at a time.
            if query.get("license_id") is None:
                raise Problem(
                    "validation_failed",
                    "license_id is required",
                    data={"fields": {"license_id": ["Выберите лицензию."]}},
                )
            get_license(query["license_id"], customer_id=scope)
        count, items = list_activations(**query)
        return Response(
            {"count": count, "results": [s.ActivationSerializer(asdict(i)).data for i in items]}
        )


class ActivationReleaseView(_Operator):
    @extend_schema(
        parameters=[ACTIVATION_ID],
        request=s.ReasonSerializer,
        responses={200: s.ActivationSerializer},
        operation_id="activations_release",
    )
    def post(self, request: Request, activation_id: str) -> Response:
        data = valid(s.ReasonSerializer(data=request.data))
        result = release_by_operator(activation_id, reason=data["reason"], **self.context(request))
        return Response(s.ActivationSerializer(asdict(result)).data)


class ActivationDirectivesView(_Operator):
    """Directives of an activation (section 8 of document 2): sent with the next check."""

    @extend_schema(
        parameters=[ACTIVATION_ID],
        responses={200: s.DirectiveSerializer(many=True)},
        operation_id="activations_directives_list",
    )
    def get(self, request: Request, activation_id: str) -> Response:
        return Response(
            [s.DirectiveSerializer(asdict(d)).data for d in directives_of(activation_id)]
        )

    @extend_schema(
        parameters=[ACTIVATION_ID],
        request=s.DirectiveCreateSerializer,
        responses={201: s.DirectiveSerializer},
        operation_id="activations_directives_create",
    )
    def post(self, request: Request, activation_id: str) -> Response:
        data = valid(s.DirectiveCreateSerializer(data=request.data))
        result = issue_directive(
            activation_id, data["type"], data["params"], **self.context(request)
        )
        return Response(s.DirectiveSerializer(asdict(result)).data, status=201)


class LicenseDirectivesView(_Operator):
    @extend_schema(
        parameters=[LICENSE_ID],
        request=s.DirectiveCreateSerializer,
        responses={200: s.DirectivesQueuedSerializer},
        operation_id="licenses_directives_create",
    )
    def post(self, request: Request, license_id: UUID) -> Response:
        data = valid(s.DirectiveCreateSerializer(data=request.data))
        queued = issue_license_directive(
            license_id, data["type"], data["params"], **self.context(request)
        )
        return Response({"queued": queued})


class ProductsView(_Reader):
    @extend_schema(responses={200: s.ProductSerializer(many=True)}, operation_id="products_list")
    def get(self, request: Request) -> Response:
        return Response([s.ProductSerializer(product).data for product in list_products()])
