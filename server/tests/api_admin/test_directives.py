"""Directives from the console (section 8 of document 2): queued by an operator, sent with the
next check until the product acks them, every one audited."""

from collections.abc import Iterator
from typing import Any

import pytest

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import sign_in
from tests.api_product.test_activate import activate, request_body
from tests.api_product.test_check import check, check_body

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def activation(licensed: Any, issuer: Any) -> str:
    reply = activate(request_body())
    assert reply.status_code == 201
    activation_id: str = reply.json()["activation_id"]
    return activation_id


def test_operator_queues_and_the_product_acks(activation: str, clock: FrozenClock) -> None:
    from apps.audit.models import AuditEvent

    console = sign_in("operator", clock)
    path = f"/api/admin/activations/{activation}/directives"
    url = {
        "type": "set_server_url",
        "params": {"url": "https://license.corp.local/", "fallback_days": 7},
    }
    created = console.post(path, url)
    assert created.status_code == 201, created.content
    directive = created.json()
    assert directive["state"] == "queued"
    assert directive["params"] == {"url": "https://license.corp.local", "fallback_days": 7}
    assert AuditEvent.objects.filter(action="directive.queued", object_id=activation).exists()

    first = check(activation, check_body())
    assert first.status_code == 200
    assert [d["id"] for d in first.json()["directives"]] == [directive["id"]]
    acked = check(activation, check_body(lease_seq=2, acked_directives=[directive["id"]]))
    assert acked.json()["directives"] == []
    [listed] = console.get(path).json()
    assert listed["state"] == "acked" and listed["done_at"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"type": "collect_diagnostics"}, "type"),
        ({"type": "set_check_interval", "params": {"hours": 0}}, "hours"),
        ({"type": "set_server_url", "params": {"url": "http://plain.example"}}, "url"),
        ({"type": "show_message", "params": {"message": {"text": {"ru": ""}}}}, "text"),
        (
            {
                "type": "show_message",
                "params": {"message": {"text": {"ru": "x"}, "placement": "x"}},
            },
            "message",
        ),
    ],
)
def test_parameters_are_checked(activation: str, clock: FrozenClock, body: Any, field: str) -> None:
    reply = sign_in("operator", clock).post(f"/api/admin/activations/{activation}/directives", body)
    assert reply.status_code == 400
    assert field in reply.json()["data"]["fields"]


def test_show_message_gets_an_id_and_defaults(activation: str, clock: FrozenClock) -> None:
    body = {
        "type": "show_message",
        "params": {"message": {"text": {"ru": "Плановые работы 10.11."}}},
    }
    reply = sign_in("operator", clock).post(f"/api/admin/activations/{activation}/directives", body)
    message = reply.json()["params"]["message"]
    assert message["id"].startswith("ops.")
    assert (message["severity"], message["placement"], message["repeat"]) == (
        "info",
        "dialog",
        "once",
    )


def test_licence_wide_directive_and_rights(
    activation: str, licensed: Any, clock: FrozenClock
) -> None:
    body = {"type": "refresh_now"}
    viewer = sign_in("customer_viewer", clock)
    assert viewer.post(f"/api/admin/licenses/{licensed.id}/directives", body).status_code == 403
    reply = sign_in("operator", clock).post(f"/api/admin/licenses/{licensed.id}/directives", body)
    assert reply.json() == {"queued": 1}
    assert [d["type"] for d in check(activation, check_body()).json()["directives"]] == [
        "refresh_now"
    ]


def test_released_activation_gets_no_directives(activation: str, clock: FrozenClock) -> None:
    console = sign_in("operator", clock)
    console.post(f"/api/admin/activations/{activation}/release", {"reason": "замена ПК"})
    reply = console.post(f"/api/admin/activations/{activation}/directives", {"type": "refresh_now"})
    assert reply.status_code == 400
