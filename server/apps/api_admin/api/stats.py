"""Admin API: statistics of licences and its XLSX export (E10-01, E10-02)."""

from dataclasses import asdict

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import valid
from apps.api_admin.api.licenses import _Reader
from apps.stats.domain import license_stats, stats_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StatsView(_Reader):
    @extend_schema(
        parameters=[s.StatsQuerySerializer],
        responses={200: s.StatsSerializer},
        operation_id="stats_get",
    )
    def get(self, request: Request) -> Response:
        query = valid(s.StatsQuerySerializer(data=request.query_params))
        query["customer_id"] = self.scope(request) or query.get("customer_id")
        return Response(s.StatsSerializer(asdict(license_stats(**query))).data)


class StatsExportView(_Reader):
    @extend_schema(
        parameters=[s.StatsQuerySerializer],
        responses={200: OpenApiResponse(OpenApiTypes.BINARY, description="XLSX")},
        operation_id="stats_export",
    )
    def get(self, request: Request) -> HttpResponse:
        query = valid(s.StatsQuerySerializer(data=request.query_params))
        query["customer_id"] = self.scope(request) or query.get("customer_id")
        response = HttpResponse(stats_workbook(**query), content_type=XLSX)
        response["Content-Disposition"] = 'attachment; filename="almi-stats.xlsx"'
        return response
