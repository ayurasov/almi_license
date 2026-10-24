"""Admin API: catalog and policy profiles (E01-02, E01-03, E07-06)."""

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import valid
from apps.api_admin.api.licenses import _Operator
from apps.catalog.domain import (
    add_capability,
    create_metric,
    create_product,
    list_metrics,
    list_profiles,
    product_details,
    profile_versions,
    save_edition,
    save_profile,
    update_capability,
    update_product,
)

PRODUCT_ID = OpenApiParameter("product_id", str, OpenApiParameter.PATH)
CAPABILITY = OpenApiParameter("code", str, OpenApiParameter.PATH)
PROFILE = OpenApiParameter("code", str, OpenApiParameter.PATH)


def _product(data: dict[str, Any]) -> dict[str, Any]:
    return dict(s.ProductDetailsSerializer(data).data)


class MetricsView(_Operator):
    @extend_schema(responses={200: s.MetricSerializer(many=True)}, operation_id="metrics_list")
    def get(self, request: Request) -> Response:
        return Response([s.MetricSerializer(m).data for m in list_metrics()])

    @extend_schema(
        request=s.MetricCreateSerializer,
        responses={201: s.MetricSerializer},
        operation_id="metrics_create",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.MetricCreateSerializer(data=request.data))
        return Response(s.MetricSerializer(create_metric(data, **self.context(request))).data, 201)


class CatalogProductsView(_Operator):
    @extend_schema(
        request=s.ProductCreateSerializer,
        responses={201: s.ProductDetailsSerializer},
        operation_id="products_create",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.ProductCreateSerializer(data=request.data))
        return Response(_product(create_product(data, **self.context(request))), status=201)


class ProductView(_Operator):
    @extend_schema(
        parameters=[PRODUCT_ID],
        responses={200: s.ProductDetailsSerializer},
        operation_id="products_get",
    )
    def get(self, request: Request, product_id: UUID) -> Response:
        return Response(_product(product_details(product_id)))

    @extend_schema(
        parameters=[PRODUCT_ID],
        request=s.ProductUpdateSerializer,
        responses={200: s.ProductDetailsSerializer},
        operation_id="products_update",
    )
    def patch(self, request: Request, product_id: UUID) -> Response:
        data = valid(s.ProductUpdateSerializer(data=request.data, partial=True))
        return Response(_product(update_product(product_id, data, **self.context(request))))


class CapabilitiesView(_Operator):
    @extend_schema(
        parameters=[PRODUCT_ID],
        request=s.CapabilityCreateSerializer,
        responses={201: s.ProductDetailsSerializer},
        operation_id="capabilities_create",
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        data = valid(s.CapabilityCreateSerializer(data=request.data))
        result = add_capability(product_id, data, **self.context(request))
        return Response(_product(result), status=201)


class CapabilityView(_Operator):
    @extend_schema(
        parameters=[PRODUCT_ID, CAPABILITY],
        request=s.CapabilityUpdateSerializer,
        responses={200: s.ProductDetailsSerializer},
        operation_id="capabilities_update",
    )
    def patch(self, request: Request, product_id: UUID, code: str) -> Response:
        data = valid(s.CapabilityUpdateSerializer(data=request.data, partial=True))
        result = update_capability(product_id, code, data, **self.context(request))
        return Response(_product(result))


class EditionsView(_Operator):
    @extend_schema(
        parameters=[PRODUCT_ID],
        request=s.EditionSaveSerializer,
        responses={200: s.ProductDetailsSerializer},
        operation_id="editions_save",
    )
    def post(self, request: Request, product_id: UUID) -> Response:
        data = valid(s.EditionSaveSerializer(data=request.data))
        return Response(_product(save_edition(product_id, data, **self.context(request))))


class ProfilesView(_Operator):
    @extend_schema(responses={200: s.ProfileSerializer(many=True)}, operation_id="profiles_list")
    def get(self, request: Request) -> Response:
        return Response([s.ProfileSerializer(p).data for p in list_profiles()])


class ProfileView(_Operator):
    @extend_schema(
        parameters=[PROFILE],
        responses={200: s.ProfileSerializer(many=True)},
        operation_id="profiles_versions",
    )
    def get(self, request: Request, code: str) -> Response:
        """Versions of the profile, newest first."""
        return Response([s.ProfileSerializer(p).data for p in profile_versions(code)])

    @extend_schema(
        parameters=[PROFILE],
        request=s.ProfileSaveSerializer,
        responses={200: s.ProfileSerializer},
        operation_id="profiles_save",
    )
    def post(self, request: Request, code: str) -> Response:
        """A new version of the profile (or the first one); unchanged parameters add nothing."""
        data = valid(s.ProfileSaveSerializer(data=request.data))
        profile = save_profile(code, data["params"], **self.context(request))
        return Response(s.ProfileSerializer(profile).data)
