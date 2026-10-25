"""Admin API: import of an LK export — upload and preview, article mapping, confirmation
(E06-01…E06-03, E07-07)."""

from dataclasses import asdict
from pathlib import PurePath
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import valid
from apps.api_admin.api.licenses import _Operator
from apps.licensing.domain import (
    ImportFileError,
    apply_import,
    list_mappings,
    parse_lk_export,
    save_mapping,
)
from infra.clock import current_clock
from infra.problems import Problem

SESSION_ID = OpenApiParameter("session_id", str, OpenApiParameter.PATH)
AA = OpenApiParameter("aa", str, OpenApiParameter.PATH)


class ImportsView(_Operator):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": s.ImportUploadSerializer},
        responses={201: s.ImportPreviewSerializer},
        operation_id="imports_create",
    )
    def post(self, request: Request) -> Response:
        """Preview of the XLSX export; nothing is written to licenses until the confirmation."""
        upload = valid(s.ImportUploadSerializer(data=request.data))["file"]
        try:
            name = PurePath(upload.name or "export.xlsx").name[:255]
            preview = parse_lk_export(upload.read(), filename=name, now=current_clock().now())
        except ImportFileError as error:
            raise Problem(
                "invalid_request", "import file refused", data={"fields": {"file": [str(error)]}}
            ) from None
        return Response(s.ImportPreviewSerializer(asdict(preview)).data, status=201)


class ImportApplyView(_Operator):
    @extend_schema(
        parameters=[SESSION_ID],
        request=None,
        responses={200: s.ImportReportSerializer},
        operation_id="imports_apply",
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        report = apply_import(session_id, **self.context(request))
        return Response(s.ImportReportSerializer(asdict(report)).data)


class ArticleMappingsView(_Operator):
    @extend_schema(
        responses={200: s.ArticleMappingSerializer(many=True)}, operation_id="mappings_list"
    )
    def get(self, request: Request) -> Response:
        return Response([s.ArticleMappingSerializer(asdict(m)).data for m in list_mappings()])


class ArticleMappingView(_Operator):
    @extend_schema(
        parameters=[AA],
        request=s.ArticleMappingWriteSerializer,
        responses={200: s.ArticleMappingSerializer},
        operation_id="mappings_save",
    )
    def put(self, request: Request, aa: str) -> Response:
        data = valid(s.ArticleMappingWriteSerializer(data=request.data))
        mapping = save_mapping(aa, data, **self.context(request))
        return Response(s.ArticleMappingSerializer(asdict(mapping)).data)
