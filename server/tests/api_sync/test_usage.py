"""E09-05, E09-06: usage report .alk-usage of a local server and the receipt of the central one.

The central and the local server share the test database (as in test_local_flow.py).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from infra.clock import FrozenClock
from infra.crypto.encoding import b64url_decode, b64url_encode
from tests.api_admin.session import sign_in
from tests.api_product.test_activate import activate, request_body
from tests.api_sync.local import claims, header
from tests.api_sync.test_local_flow import (  # noqa: F401 - fixtures
    CENTRAL,
    central_code,
    central_transport,
    forget_central,
    local_settings,
    server_clock,
)
from tests.contract import schema_errors

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def one_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seats given to the local server are not subtracted again on its own side of the test DB."""
    import apps.activation.domain.service as service

    monkeypatch.setattr(service, "allocated_seats", lambda license_id: 0)


def online(licensed: Any, clock: FrozenClock, issuer: Any) -> Any:
    from apps.packages.domain import local_status, setup
    from apps.signing.domain import install_provider

    code = central_code(licensed, clock)
    setup(registration_code=code, central_url=CENTRAL, actor="user:admin", now=clock.now())
    install_provider(issuer)  # setup() resets the provider; the central side signs receipts
    return local_status()


def test_online_report_and_receipt(
    licensed: Any,
    issuer: Any,
    clock: FrozenClock,
    central_transport: list[str],  # noqa: F811
    local_settings: None,  # noqa: F811
    tmp_path: Path,
) -> None:
    from apps.packages.domain import report_state, send_report
    from apps.packages.models import LocalIdentity, UsageReport

    status = online(licensed, clock, issuer)
    assert activate(request_body()).status_code == 201
    assert send_report(now=clock.now()) == 1
    assert central_transport[-1] == f"POST /api/sync/v1/servers/{status.server_id}/usage"

    report = UsageReport.objects.get()
    data = {k: v for k, v in report.data.items() if k != "_digest"}
    assert schema_errors("alk-usage", data) == []
    [item] = data["licenses"]
    assert (item["license_id"], item["active"], item["released"]) == (str(licensed.id), 1, 0)
    assert data["package_seq"] == 1 and data["audit_digest"]
    assert len(data["activations"]) == 1
    assert "instance_id" not in json.dumps(data["activations"])  # only its hash

    identity = LocalIdentity.objects.get()
    receipt = claims(identity.receipt)
    assert (receipt["type"], receipt["server_id"], receipt["report_seq"]) == (
        "usage",
        status.server_id,
        1,
    )
    assert schema_errors("receipt", receipt) == []
    state = report_state()
    assert state is not None and (state.report_seq, state.receipt_seq) == (1, 1)

    # The next report starts where the previous one ended.
    assert send_report(now=clock.now()) == 2
    second = UsageReport.objects.get(seq=2)
    assert second.period_from == report.period_to

    # The central statistics show the seats used on the local server.
    with override_settings(DEPLOYMENT_MODE="central"):
        from apps.stats.domain import license_stats

        assert license_stats().rows[0].local_active == 1


def test_files_report_receipt_in_the_next_package(
    licensed: Any,
    issuer: Any,
    clock: FrozenClock,
    central_transport: list[str],  # noqa: F811
    local_settings: None,  # noqa: F811
) -> None:
    from apps.packages.domain import import_package, report_state
    from apps.packages.models import LocalIdentity, LocalServer

    online(licensed, clock, issuer)
    LocalIdentity.objects.update(exchange="files")
    local_console = sign_in("operator", clock)
    built = local_console.post("/api/admin/usage-report")
    assert built.status_code == 200, built.content
    assert built["Content-Disposition"] == 'attachment; filename="usage-1.alk-usage"'
    content = built.content
    assert header(json.loads(content)["payload"])["typ"] == "alm-usage+jws"

    with override_settings(DEPLOYMENT_MODE="central"):
        central = sign_in("admin", clock)

        def upload(data: bytes) -> Any:
            return central.client.post(
                "/api/admin/local-servers/usage-file",
                {"file": SimpleUploadedFile("usage-1.alk-usage", data)},
                HTTP_X_CSRFTOKEN=central.token,
            )

        first = upload(content)
        assert first.status_code == 200, first.content
        assert first.json()["report_seq"] == 1
        assert upload(content).json()["receipt"] == first.json()["receipt"]  # idempotent

        document = json.loads(content)
        head, payload, sig = document["payload"].split(".")
        broken = bytearray(b64url_decode(sig))
        broken[0] ^= 1  # one bit: always another, invalid signature
        forged = json.dumps(
            document | {"payload": f"{head}.{payload}.{b64url_encode(bytes(broken))}"}
        ).encode()
        assert upload(forged).json()["code"] == "signature_invalid"

        from apps.packages.domain import package_since

        server = LocalServer.objects.get()
        new_package = package_since(server.external_id, 1, now=clock.now())
    assert new_package is not None
    assert claims(new_package["payload"])["usage_receipt"]["report_seq"] == 1
    import_package(new_package, actor="user:op", now=clock.now())
    state = report_state()
    assert state is not None and state.receipt_seq == 1


def test_seq_and_content_checks(
    licensed: Any,
    issuer: Any,
    clock: FrozenClock,
    central_transport: list[str],  # noqa: F811
    local_settings: None,  # noqa: F811
) -> None:
    from apps.packages.domain import accept_usage, build_report
    from apps.packages.models import LocalIdentity
    from infra.errors import DomainError

    online(licensed, clock, issuer)
    LocalIdentity.objects.update(exchange="files")
    first, _ = build_report(actor="user:op", now=clock.now())
    second, _ = build_report(actor="user:op", now=clock.now())
    with override_settings(DEPLOYMENT_MODE="central"):
        accept_usage(json.dumps(second).encode(), now=clock.now())
        with pytest.raises(DomainError) as older:
            accept_usage(json.dumps(first).encode(), now=clock.now())
        assert older.value.code == "idempotency_conflict"
        with pytest.raises(DomainError) as other_server:
            accept_usage(json.dumps(second).encode(), now=clock.now(), server_id="srv_other")
        assert other_server.value.code == "signature_invalid"
        forget_central()
        with pytest.raises(DomainError) as unknown:
            accept_usage(json.dumps(second).encode(), now=clock.now())
        assert unknown.value.code == "signature_invalid"
