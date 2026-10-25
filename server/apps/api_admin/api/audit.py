"""Admin API: the audit journal with filters and its CSV export (E10-04).

A customer viewer sees the events of its licences and their activations only (E07-08).
"""

from dataclasses import asdict
from typing import Any

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.activation.domain import customer_objects
from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import valid
from apps.api_admin.api.licenses import _Reader
from apps.audit.domain import EventFilter, events_csv, search_events
from apps.licensing.domain import find_licenses


class _Journal(_Reader):
    def query(self, request: Request) -> tuple[EventFilter, dict[str, Any]]:
        data = valid(s.AuditQuerySerializer(data=request.query_params))
        paging = {"page": data.pop("page"), "page_size": data.pop("page_size")}
        scope = self.scope(request)
        objects = None
        if scope is not None:
            objects = customer_objects([lic.id for lic in find_licenses(customer_id=scope)])
        return EventFilter(**data, objects=objects), paging


class AuditView(_Journal):
    @extend_schema(
        parameters=[s.AuditQuerySerializer],
        responses={200: s.AuditPageSerializer},
        operation_id="audit_list",
    )
    def get(self, request: Request) -> Response:
        query, paging = self.query(request)
        count, events = search_events(query, **paging)
        return Response(
            {"count": count, "results": [s.AuditEventSerializer(asdict(e)).data for e in events]}
        )


class AuditExportView(_Journal):
    @extend_schema(
        parameters=[s.AuditQuerySerializer],
        responses={200: OpenApiResponse(OpenApiTypes.BINARY, description="CSV")},
        operation_id="audit_export",
    )
    def get(self, request: Request) -> HttpResponse:
        query, _ = self.query(request)
        response = HttpResponse(events_csv(query), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="almi-audit.csv"'
        return response
