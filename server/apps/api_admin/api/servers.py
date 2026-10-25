"""Admin API: local servers of customers on the central server (E09-02)."""

from dataclasses import asdict
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api_admin.api import serializers as s
from apps.api_admin.api.common import valid
from apps.api_admin.api.licenses import _Operator
from apps.packages.domain import (
    create_server,
    list_servers,
    new_code,
    register_from_file,
    set_allocations,
)
from infra.clock import current_clock

SERVER = OpenApiParameter("server_uuid", str, OpenApiParameter.PATH)


class LocalServersView(_Operator):
    @extend_schema(
        parameters=[OpenApiParameter("customer_id", str, required=False)],
        responses={200: s.LocalServerSerializer(many=True)},
        operation_id="local_servers_list",
    )
    def get(self, request: Request) -> Response:
        raw = request.query_params.get("customer_id")
        customer = UUID(raw) if raw else None
        return Response(
            [
                s.LocalServerSerializer(asdict(x)).data
                for x in list_servers(customer, now=current_clock().now())
            ]
        )

    @extend_schema(
        request=s.LocalServerCreateSerializer,
        responses={201: s.RegistrationCodeSerializer},
        operation_id="local_servers_create",
    )
    def post(self, request: Request) -> Response:
        data = valid(s.LocalServerCreateSerializer(data=request.data))
        issued = create_server(
            data["customer_id"], data["name"], data["allocations"], **self.context(request)
        )
        return Response(s.RegistrationCodeSerializer(asdict(issued)).data, status=201)


class LocalServerCodeView(_Operator):
    @extend_schema(
        parameters=[SERVER],
        request=None,
        responses={200: s.RegistrationCodeSerializer},
        operation_id="local_servers_new_code",
    )
    def post(self, request: Request, server_uuid: UUID) -> Response:
        issued = new_code(server_uuid, **self.context(request))
        return Response(s.RegistrationCodeSerializer(asdict(issued)).data)


class LocalServerAllocationsView(_Operator):
    @extend_schema(
        parameters=[SERVER],
        request=s.AllocationsSerializer,
        responses={200: s.LocalServerSerializer},
        operation_id="local_servers_allocations",
    )
    def put(self, request: Request, server_uuid: UUID) -> Response:
        data = valid(s.AllocationsSerializer(data=request.data))
        server = set_allocations(server_uuid, data["allocations"], **self.context(request))
        return Response(s.LocalServerSerializer(asdict(server)).data)


class LocalServerRegisterFileView(_Operator):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": s.ImportUploadSerializer},
        responses={200: s.AlkFileSerializer},
        operation_id="local_servers_register_file",
    )
    def post(self, request: Request) -> Response:
        """A .alk-req of type server in, the first package .alk out (closed networks)."""
        upload = valid(s.ImportUploadSerializer(data=request.data))["file"]
        server_id, document = register_from_file(
            upload.read(), now=current_clock().now(), ip=request.META.get("REMOTE_ADDR")
        )
        response = Response(document)
        response["Content-Disposition"] = f'attachment; filename="{server_id}.alk"'
        return response
