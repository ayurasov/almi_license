"""Admin API of a local server: first-run wizard and package exchange (E09-01, E09-03)."""

import json
from dataclasses import asdict
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import actor_of, valid
from apps.api_admin.api.permissions import ConsoleSession, IsAdmin, IsOperator
from apps.packages.domain import build_report, import_package, local_status, setup, sync_package
from infra.clock import current_clock
from infra.problems import Problem

MAX_PACKAGE_BYTES = 16 * 1024 * 1024


def _context(request: Request) -> dict[str, Any]:
    return {
        "actor": actor_of(request),
        "now": current_clock().now(),
        "ip": request.META.get("REMOTE_ADDR"),
    }


class SetupView(APIView):
    """The first-run wizard: registration code and the central server or files only."""

    authentication_classes = [ConsoleSession]
    permission_classes = [IsAdmin]

    @extend_schema(responses={200: s.LocalStatusSerializer}, operation_id="local_status")
    def get(self, request: Request) -> Response:
        return Response(s.LocalStatusSerializer(asdict(local_status(current_clock().now()))).data)

    @extend_schema(
        request=s.SetupRequestSerializer,
        responses={200: s.SetupResultSerializer},
        operation_id="local_setup",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.SetupRequestSerializer(data=request.data))
        result = setup(
            registration_code=data["registration_code"],
            central_url=data["central_url"] or None,
            **_context(request),
        )
        return Response(s.SetupResultSerializer(asdict(result)).data)


class PackageUploadView(APIView):
    """A package .alk brought on a medium (files mode, or a replacement in online mode)."""

    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": s.ImportUploadSerializer},
        responses={200: s.LocalStatusSerializer},
        operation_id="local_package_upload",
    )
    def post(self, request: Request) -> Response:
        upload = valid(s.ImportUploadSerializer(data=request.data))["file"]
        if upload.size is None or upload.size > MAX_PACKAGE_BYTES:
            raise Problem("invalid_request", "package file is too large")
        try:
            document = json.loads(upload.read())
        except ValueError:
            raise Problem(
                "invalid_request",
                "not JSON",
                data={"fields": {"file": ["Это не файл пакета .alk."]}},
            ) from None
        status = import_package(document, **_context(request))
        return Response(s.LocalStatusSerializer(asdict(status)).data)


class PackageSyncView(APIView):
    """Ask the central server for a newer package now (online mode)."""

    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]

    @extend_schema(
        request=None, responses={200: s.LocalStatusSerializer}, operation_id="local_package_sync"
    )
    def post(self, request: Request) -> Response:
        sync_package(now=current_clock().now())
        return Response(s.LocalStatusSerializer(asdict(local_status(current_clock().now()))).data)


class UsageReportView(APIView):
    """A new usage report .alk-usage of this server as a file (files exchange, E09-05)."""

    authentication_classes = [ConsoleSession]
    permission_classes = [IsOperator]

    @extend_schema(
        request=None, responses={200: s.AlkFileSerializer}, operation_id="local_usage_report"
    )
    def post(self, request: Request) -> Response:
        context = _context(request)
        document, seq = build_report(actor=context["actor"], now=context["now"])
        response = Response(document)
        response["Content-Disposition"] = f'attachment; filename="usage-{seq}.alk-usage"'
        return response
