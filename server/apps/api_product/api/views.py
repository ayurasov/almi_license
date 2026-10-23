"""Product API v1 views: parse, call the domain, shape the response (AGENTS.md, rule 2)."""

from typing import Any, cast

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.activation.domain import ActivationRequest, activate
from apps.activation.domain.leases import rfc3339
from apps.api_product.api.serializers import ActivateRequestSerializer
from apps.api_product.auth import DeviceSignatureAuthentication, SignedRequest
from infra.clock import current_clock
from infra.problems import Problem


def _valid(serializer_class: type[ActivateRequestSerializer], request: Request) -> dict[str, Any]:
    serializer = serializer_class(data=request.data)
    if not serializer.is_valid():
        raise Problem("invalid_request", "request body does not match the schema")
    data: dict[str, Any] = serializer.validated_data
    return data


class ActivateView(APIView):
    """POST /api/v1/activations (operationId activate, section 5.2 of document 2)."""

    authentication_classes = [DeviceSignatureAuthentication]
    signature_allows_device_key = True

    def post(self, request: Request) -> Response:
        data = _valid(ActivateRequestSerializer, request)
        signed = cast(SignedRequest, request.auth)
        if data["device_pubkey"] != signed.public_key:
            raise Problem("signature_invalid")
        product, instance = data["product"], data["instance"]
        now = current_clock().now()
        result = activate(
            ActivationRequest(
                license_key=data["license_key"],
                product_code=product["code"],
                product_version=product["version"],
                edition=product.get("edition"),
                instance_id=instance["instance_id"],
                subject_type=instance["subject_type"],
                instance_name=instance.get("name", ""),
                os=dict(instance["os"]),
                fingerprint={
                    "scheme": data["fingerprint"]["scheme"],
                    "components": dict(data["fingerprint"]["components"]),
                },
                device_pubkey=data["device_pubkey"],
                ip=request.META.get("REMOTE_ADDR"),
            ),
            now=now,
            issuer=settings.LEASE_ISSUER,
        )
        return Response(
            {
                "activation_id": result.activation_id,
                "status": "active",
                "lease": result.lease,
                "next_check_at": rfc3339(result.policy.next_check_at),
                "server_time": rfc3339(now),
                "messages": [],
                "directives": [],
            },
            status=201 if result.created else 200,
        )
