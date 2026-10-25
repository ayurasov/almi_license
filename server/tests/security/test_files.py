"""E16-06: files of other parties and oversized files (criterion 12, section 13 of document 1).

The package of another local server (another customer) is refused by a local server; files above
their limits are refused before they are parsed.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import sign_in
from tests.api_admin.test_local_servers import server_request
from tests.api_sync.local import LocalServerClient
from tests.api_sync.test_local_flow import central_code, local_settings  # noqa: F401 - fixture

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def test_package_of_another_local_server_is_refused(
    licensed: Any,
    issuer: Any,
    clock: FrozenClock,
    local_settings: None,  # noqa: F811
) -> None:
    from apps.packages.domain import import_package, register_from_file, setup
    from infra.errors import DomainError

    # The server of this customer registers by file (its own identity on the local side).
    setup(
        registration_code=central_code(licensed, clock),
        central_url=None,
        actor="a",
        now=clock.now(),
    )
    # Another server registers on the central one and gets its own package.
    other = LocalServerClient()
    with override_settings(DEPLOYMENT_MODE="central"):
        from apps.packages.domain import create_server

        code = create_server(
            licensed.customer_id, "Другой ЦОД", {str(licensed.id): 1}, actor="op", now=clock.now()
        ).code
        _, foreign = register_from_file(server_request(other, code), now=clock.now())
    with pytest.raises(DomainError) as refused:
        import_package(foreign, actor="a", now=clock.now())
    assert refused.value.code in {"invalid_request", "signature_invalid"}


def test_oversized_files_are_refused_before_parsing(licensed: Any, clock: FrozenClock) -> None:
    console = sign_in("operator", clock)
    big = SimpleUploadedFile("big.alk-usage", b"{" + b" " * (16 * 1024 * 1024) + b"}")
    usage = console.client.post(
        "/api/admin/local-servers/usage-file", {"file": big}, HTTP_X_CSRFTOKEN=console.token
    )
    assert usage.status_code in {400, 413}, usage.content
    request = SimpleUploadedFile("big.alk-req", json.dumps({"x": "y" * 70_000}).encode())
    offline = console.client.post("/api/v1/offline/requests", {"file": request})
    assert (offline.status_code, offline.json()["code"]) == (400, "invalid_request")
