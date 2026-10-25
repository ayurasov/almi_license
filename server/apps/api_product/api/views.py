"""Product API v1 views: parse, call the domain, shape the response (AGENTS.md, rule 2)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

from django.conf import settings
from django.http import HttpResponse
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from apps.activation.domain import (
    MAX_FILE_BYTES,
    ActivationRequest,
    ActivationResult,
    CheckRequest,
    OfflineRequest,
    activate,
    answer,
    check,
    open_request,
    release,
)
from apps.activation.domain.leases import rfc3339
from apps.api_product.api.serializers import (
    ActivateRequestSerializer,
    CheckRequestSerializer,
    OfflineActivateSerializer,
    OfflineDeviceSerializer,
    ReleaseRequestSerializer,
)
from apps.api_product.auth import DeviceSignatureAuthentication, SignedRequest
from apps.api_product.domain.idempotency import (
    InvalidKey,
    KeyConflict,
    Stored,
    remember,
    replay,
)
from apps.api_product.domain.limits import limit_activation, limit_check, limit_offline
from apps.api_product.domain.ratelimit import Limited
from apps.packages.domain import local_server_id
from apps.signing.domain import TrustUnavailable, trust_document
from infra.clock import current_clock
from infra.problems import Problem

# Multipart boundaries and part headers around a file of at most MAX_FILE_BYTES.
MULTIPART_OVERHEAD = 8 * 1024
# The oldest DL module that speaks protocol 1 (section 5.1 of document 2).
MIN_SDK_VERSION = "1.0.0"


def _valid(serializer_class: type[Serializer[dict[str, Any]]], request: Request) -> dict[str, Any]:
    return _valid_data(serializer_class, request.data)


def _valid_data(serializer_class: type[Serializer[dict[str, Any]]], body: Any) -> dict[str, Any]:
    serializer = serializer_class(data=body)
    if not serializer.is_valid():
        raise Problem("invalid_request", "request body does not match the schema")
    data: dict[str, Any] = serializer.validated_data
    return data


@contextmanager
def _limited() -> Iterator[None]:
    """A limit of section 4.7 becomes 429 rate_limited with Retry-After."""
    try:
        yield
    except Limited as limited:
        raise Problem("rate_limited", retry_after=limited.retry_after) from None


class _Replayed(Exception):
    def __init__(self, stored: Stored) -> None:
        super().__init__("idempotent replay")
        self.stored = stored


class IdempotentView(APIView):
    """Idempotency-Key (E05-02): the first response is kept 24 hours and returned to a repeat.

    The header is optional on the server (a tolerant reader); the DL module always sends it.
    """

    def _idempotency(self, request: Request) -> tuple[str, str] | None:
        key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        signed = request.auth
        if not key or not isinstance(signed, SignedRequest):
            return None
        # The device key, not the keyid: every activation request has keyid "device".
        return signed.public_key, key

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        scope = self._idempotency(request)
        if scope is None:
            return
        try:
            stored = replay(*scope, request._request.body, now=current_clock().now())
        except InvalidKey:
            raise Problem("invalid_request", "Idempotency-Key must be a UUID") from None
        except KeyConflict:
            raise Problem("idempotency_conflict") from None
        if stored is not None:
            raise _Replayed(stored)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, _Replayed):
            replayed = HttpResponse(
                exc.stored.body, status=exc.stored.status, content_type=exc.stored.content_type
            )
            replayed.idempotent_replay = True  # type: ignore[attr-defined]
            return replayed  # type: ignore[return-value]
        return super().handle_exception(exc)

    def finalize_response(self, request: Request, response: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().finalize_response(request, response, *args, **kwargs)
        scope = self._idempotency(request)
        if scope is None or getattr(response, "idempotent_replay", False):
            return response
        rendered = response.render() if hasattr(response, "render") else response
        remember(
            *scope,
            request.path,
            request._request.body,
            Stored(
                rendered.status_code,
                rendered.get("Content-Type", "application/json"),
                rendered.content,
            ),
            now=current_clock().now(),
        )
        return rendered


class ActivateView(IdempotentView):
    """POST /api/v1/activations (operationId activate, section 5.2 of document 2)."""

    authentication_classes = [DeviceSignatureAuthentication]
    signature_allows_device_key = True

    def post(self, request: Request) -> Response:
        data = _valid(ActivateRequestSerializer, request)
        signed = cast(SignedRequest, request.auth)
        if data["device_pubkey"] != signed.public_key:
            raise Problem("signature_invalid")
        now = current_clock().now()
        with _limited():
            limit_activation(
                ip=request.META.get("REMOTE_ADDR"), license_key=data["license_key"], now=now
            )
        result = activate(
            _activation_request(data, request.META.get("REMOTE_ADDR")),
            now=now,
            issuer=settings.LEASE_ISSUER,
        )
        return _lease_response(result, now, 201 if result.created else 200)


def _fingerprint(data: dict[str, Any]) -> dict[str, Any]:
    return {"scheme": data["scheme"], "components": dict(data["components"])}


def _activation_request(data: dict[str, Any], ip: str | None) -> ActivationRequest:
    product, instance = data["product"], data["instance"]
    return ActivationRequest(
        license_key=data["license_key"],
        product_code=product["code"],
        product_version=product["version"],
        edition=product.get("edition"),
        instance_id=instance["instance_id"],
        subject_type=instance["subject_type"],
        instance_name=instance.get("name", ""),
        os=dict(instance["os"]),
        fingerprint=_fingerprint(data["fingerprint"]),
        device_pubkey=data["device_pubkey"],
        ip=ip,
    )


class CheckView(APIView):
    """POST /api/v1/activations/{activation_id}/check (section 5.3 of document 2)."""

    authentication_classes = [DeviceSignatureAuthentication]

    def post(self, request: Request, activation_id: str) -> Response:
        signed = cast(SignedRequest, request.auth)
        if signed.keyid != activation_id:
            raise Problem("signature_invalid")
        data = _valid(CheckRequestSerializer, request)
        fingerprint = data.get("fingerprint")
        now = current_clock().now()
        with _limited():
            limit_check(ip=request.META.get("REMOTE_ADDR"), activation_id=activation_id, now=now)
        result = check(
            CheckRequest(
                activation_id=activation_id,
                lease_seq=data["lease_seq"],
                product_version=data["product"]["version"],
                os=dict(data["instance"]["os"]),
                fingerprint=None
                if fingerprint is None
                else {
                    "scheme": fingerprint["scheme"],
                    "components": dict(fingerprint["components"]),
                },
                usage=data.get("usage"),
                acked_directives=list(data["acked_directives"]),
                unsupported_directives=list(data["unsupported_directives"]),
                ip=request.META.get("REMOTE_ADDR"),
            ),
            now=now,
            issuer=settings.LEASE_ISSUER,
        )
        return _lease_response(result, now, 200)


class ReleaseView(IdempotentView):
    """POST /api/v1/activations/{activation_id}/release (section 5.4 of document 2, E03-05)."""

    authentication_classes = [DeviceSignatureAuthentication]

    def post(self, request: Request, activation_id: str) -> Response:
        signed = cast(SignedRequest, request.auth)
        if signed.keyid != activation_id:
            raise Problem("signature_invalid")
        data = _valid(ReleaseRequestSerializer, request)
        result = release(
            activation_id,
            reason=data["reason"],
            now=current_clock().now(),
            ip=request.META.get("REMOTE_ADDR"),
        )
        return Response(
            {
                "activation_id": result.activation_id,
                "released_at": rfc3339(result.released_at),
                "receipt": result.receipt,
            }
        )


class OfflineRequestView(APIView):
    """POST /api/v1/offline/requests (processOfflineRequest, section 10 of document 2, E08-01).

    No session and no request signature: the file itself is signed by the device key.
    """

    authentication_classes: list[type[Any]] = []
    permission_classes: list[type[Any]] = []
    parser_classes = [MultiPartParser]

    def post(self, request: Request) -> Response:
        # The size is checked before the body is read (Nginx client_max_body_size too).
        length = request.META.get("CONTENT_LENGTH") or "0"
        if not length.isdigit() or int(length) > MAX_FILE_BYTES + MULTIPART_OVERHEAD:
            raise Problem("invalid_request", "file is larger than 64 KiB")
        upload = request.FILES.get("file")
        if upload is None or upload.size is None or upload.size > MAX_FILE_BYTES:
            raise Problem("invalid_request", "a .alk-req file up to 64 KiB is required")
        now = current_clock().now()
        ip = request.META.get("REMOTE_ADDR")
        with _limited():
            limit_offline(ip=ip, now=now)
        offline = open_request(upload.read(), now=now)
        document, instance_id = _answer(offline, now, ip)
        response = Response(document)
        response["Content-Disposition"] = f'attachment; filename="{instance_id}.alk-lic"'
        return response


def _answer(offline: OfflineRequest, now: datetime, ip: str | None) -> tuple[dict[str, Any], str]:
    """The same domain services as online: activate, check (renew) and release."""
    if offline.type == "activate":
        data = _valid_data(OfflineActivateSerializer, offline.payload)
        result = activate(_activation_request(data, ip), now=now, issuer=settings.LEASE_ISSUER)
        document = answer(offline, result.activation_id, now=now, lease=result.lease)
        return document, str(data["instance"]["instance_id"])
    data = _valid_data(OfflineDeviceSerializer, offline.payload)
    instance_id = str(data["instance"]["instance_id"])
    if offline.type == "release":
        released = release(
            data["activation_id"],
            reason="uninstall",
            device_pubkey=data["device_pubkey"],
            now=now,
            ip=ip,
        )
        return answer(
            offline, released.activation_id, now=now, receipt=released.receipt
        ), instance_id
    renewed = check(
        CheckRequest(
            activation_id=data["activation_id"],
            lease_seq=0,
            product_version=data["product"]["version"],
            os=dict(data["instance"]["os"]),
            fingerprint=_fingerprint(data["fingerprint"]),
            usage=data.get("usage"),
            acked_directives=[],
            unsupported_directives=[],
            ip=ip,
        ),
        now=now,
        issuer=settings.LEASE_ISSUER,
    )
    return answer(offline, renewed.activation_id, now=now, lease=renewed.lease), instance_id


def _lease_response(result: ActivationResult, now: datetime, status: int) -> Response:
    """LeaseResponse of contracts/openapi-product-api-v1.yaml."""
    return Response(
        {
            "activation_id": result.activation_id,
            "status": "active",
            "lease": result.lease,
            "next_check_at": rfc3339(result.policy.next_check_at),
            "server_time": rfc3339(now),
            "messages": result.messages,
            "directives": result.directives,
        },
        status=status,
    )


class TrustView(APIView):
    """GET /api/v1/trust (getTrust, section 5.5 of document 2): no request signature."""

    authentication_classes: list[type[Any]] = []
    permission_classes: list[type[Any]] = []

    def get(self, request: Request) -> Response:
        try:
            return Response(trust_document(now=current_clock().now()))
        except TrustUnavailable:
            raise Problem("maintenance", "trust bundle is not available", retry_after=300) from None


class DiscoveryView(APIView):
    """GET /.well-known/almi-license (discover, section 5.1 of document 2)."""

    authentication_classes: list[type[Any]] = []
    permission_classes: list[type[Any]] = []

    def get(self, request: Request) -> Response:
        document: dict[str, Any] = {
            "service": "almi-license",
            "deployment_mode": settings.DEPLOYMENT_MODE,
            "protocol_versions": [1],
            "endpoints": {
                "activations": "/api/v1/activations",
                "trust": "/api/v1/trust",
                "events": "/api/v1/events",
                "offline_portal": "/offline",
            },
            "server_time": rfc3339(current_clock().now()),
            "min_sdk_version": MIN_SDK_VERSION,
        }
        server_id = local_server_id()
        if server_id:
            document["server_id"] = server_id
        return Response(document)
