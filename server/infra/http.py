"""Minimal HTTPS client of a local server for the Sync API of the central server (E09-02/03).

Standard library only (no new dependency): urllib with certificate verification on. A transport
can be replaced in tests.
"""

import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


Transport = Callable[[str, str, bytes, dict[str, str]], HttpResponse]


def urllib_transport(method: str, url: str, body: bytes, headers: dict[str, str]) -> HttpResponse:
    request = urllib.request.Request(  # noqa: S310  (the scheme is checked by the caller)
        url, data=body if method != "GET" else None, method=method, headers=headers
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as reply:  # noqa: S310
            return HttpResponse(reply.status, reply.read())
    except urllib.error.HTTPError as error:
        return HttpResponse(error.code, error.read())


_transport: Transport = urllib_transport


def install_transport(transport: Transport | None) -> None:
    global _transport
    _transport = transport or urllib_transport


def send(method: str, url: str, body: bytes, headers: dict[str, str]) -> HttpResponse:
    return _transport(method, url, body, headers)
