"""ALMI-Signature of Sync API requests: keyid is the server_id, the key is the server key
(section 13.2 of document 2). For registration the key comes from server_pubkey of the body,
since the central server does not know it yet."""

import json
from dataclasses import dataclass
from typing import Any

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

from apps.api_product.domain.signature import (
    ClockSkew,
    SignatureInvalid,
    parse_header,
    verify_request,
)
from apps.packages.domain import server_public_key
from infra.clock import current_clock
from infra.problems import Problem

HEADER = "HTTP_ALMI_SIGNATURE"


@dataclass(frozen=True)
class SignedServer:
    server_id: str
    public_key: str
    is_authenticated: bool = True


def _body(body: bytes) -> dict[str, Any]:
    try:
        document: Any = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise SignatureInvalid("body is not JSON") from None
    if not isinstance(document, dict):
        raise SignatureInvalid("body is not an object")
    return document


class ServerSignatureAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[SignedServer, SignedServer] | None:
        value = request.META.get(HEADER)
        if value is None:
            raise Problem("signature_invalid", "ALMI-Signature is required")
        body = request._request.body
        view = request.parser_context.get("view") if request.parser_context else None
        try:
            header = parse_header(value)
            if getattr(view, "signature_key_in_body", False):
                document = _body(body)
                key = document.get("server_pubkey")
                if document.get("server_id") != header.keyid or not isinstance(key, str):
                    raise SignatureInvalid("keyid is not the server_id of the body")
                public_key = key
            else:
                stored = server_public_key(header.keyid)
                if stored is None:
                    raise SignatureInvalid("unknown server")
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
        principal = SignedServer(server_id=header.keyid, public_key=public_key)
        return principal, principal

    def authenticate_header(self, request: Request) -> str:
        return "ALMI-Signature"
