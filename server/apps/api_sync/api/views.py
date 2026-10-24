"""Sync API v1 of the central server: registration and packages of local servers (E09-02, E09-03;
section 13 of document 2, /api/sync/v1/* of contracts/openapi-product-api-v1.yaml)."""

from typing import Any, cast

from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api_sync.api.auth import ServerSignatureAuthentication, SignedServer
from apps.packages.domain import package_since, register
from infra.clock import current_clock
from infra.problems import Problem


class RegisterSerializer(serializers.Serializer[dict[str, Any]]):
    registration_code = serializers.CharField(max_length=64)
    server_id = serializers.CharField(max_length=30)
    server_pubkey = serializers.CharField(max_length=64)
    host_fingerprint = serializers.DictField(child=serializers.CharField(max_length=128))
    version = serializers.CharField(max_length=64)


class RegisterView(APIView):
    """POST /api/sync/v1/servers/register (registerServer)."""

    authentication_classes = [ServerSignatureAuthentication]
    signature_key_in_body = True

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            raise Problem("invalid_request", "request body does not match the schema")
        data = serializer.validated_data
        result = register(**data, now=current_clock().now(), ip=request.META.get("REMOTE_ADDR"))
        return Response({"certificate": result.certificate, "package": result.package})


class PackageView(APIView):
    """GET /api/sync/v1/servers/{server_id}/package?since_seq=N (getPackage): 200 or 204."""

    authentication_classes = [ServerSignatureAuthentication]

    def get(self, request: Request, server_id: str) -> Response:
        signed = cast(SignedServer, request.auth)
        if signed.server_id != server_id:
            raise Problem("signature_invalid")
        raw = request.query_params.get("since_seq", "0")
        if not raw.isdigit():
            raise Problem("invalid_request", "since_seq is a non-negative integer")
        document = package_since(server_id, int(raw), now=current_clock().now())
        return Response(status=204) if document is None else Response(document)
