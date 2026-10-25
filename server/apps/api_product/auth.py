"""DRF authentication by the ALMI-Signature header (E05-01, section 4.4 of document 2).

keyid is the activation id, its key is Activation.device_pubkey; for activation itself the
keyid is "device" and the key comes from device_pubkey of the request body (a view allows it
with signature_allows_device_key = True). The signed body is request.body as bytes, before
any JSON parsing.
"""

import json
from dataclasses import dataclass
from typing import Any

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

from apps.activation.domain import device_public_key
from apps.api_product.domain.signature import (
    DEVICE_KEYID,
    ClockSkew,
    SignatureInvalid,
    parse_header,
    verify_request,
)
from infra.clock import current_clock
from infra.problems import Problem

HEADER = "HTTP_ALMI_SIGNATURE"


@dataclass(frozen=True)
class SignedRequest:
    """request.user and request.auth of a request with a valid signature."""

    keyid: str
    public_key: str
    is_authenticated: bool = True


def _body_key(body: bytes) -> str:
    try:
        document: Any = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise SignatureInvalid("body is not JSON") from None
    key = document.get("device_pubkey") if isinstance(document, dict) else None
    if not isinstance(key, str):
        raise SignatureInvalid("device_pubkey is missing")
    return key


class DeviceSignatureAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SignedRequest, SignedRequest] | None:
        value = request.META.get(HEADER)
        if value is None:
            return None
        body = request._request.body
        view = request.parser_context.get("view") if request.parser_context else None
        try:
            header = parse_header(value)
            if header.keyid == DEVICE_KEYID:
                if not getattr(view, "signature_allows_device_key", False):
                    raise SignatureInvalid("keyid device outside activation")
                public_key = _body_key(body)
            else:
                stored = device_public_key(header.keyid)
                if stored is None:
                    raise SignatureInvalid("unknown keyid")
                public_key = stored
            verify_request(
                header,
                method=request.method or "",
                path=request.get_full_path(),
                body=body,
                public_key=public_key,
                now=current_clock().now(),
            )
        except SignatureInvalid:
            raise Problem("signature_invalid") from None
        except ClockSkew as skew:
            raise Problem("clock_skew", server_time=skew.server_time) from None
        principal = SignedRequest(keyid=header.keyid, public_key=public_key)
        return principal, principal

    def authenticate_header(self, request: Request) -> str:
        return "ALMI-Signature"
