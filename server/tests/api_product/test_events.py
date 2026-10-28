"""POST /api/v1/events (question 36): events of the product, signed by the device key."""

from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_product.test_activate import activate, request_body
from tests.signed import dev_device_key, signed_post

pytestmark = pytest.mark.django_db
PATH = "/api/v1/events"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def activation_id(licensed: Any, issuer: Any) -> str:
    value: str = activate(request_body()).json()["activation_id"]
    return value


def send(
    activation_id: str, events: list[dict[str, Any]], signer: Ed25519PrivateKey | None = None
) -> Any:
    body = {"activation_id": activation_id, "events": events}
    return signed_post(Client(), PATH, body, signer or dev_device_key(), activation_id)


def event(n: int, kind: str = "clock_rollback_detected") -> dict[str, Any]:
    return {"id": f"ev-{n}", "type": kind, "at": "2026-11-02T08:00:00Z", "data": {"n": n}}


def test_events_are_stored_once_and_audited(activation_id: str) -> None:
    from apps.activation.models import ProductEvent
    from apps.audit.models import AuditEvent

    first = send(activation_id, [event(1), event(2, "feature_denied")])
    assert (first.status_code, first.json()) == (202, {"accepted": 2})
    again = send(activation_id, [event(1)])
    assert (again.status_code, again.json()) == (202, {"accepted": 0})
    assert ProductEvent.objects.count() == 2
    # Only signs of tampering go to the journal.
    audited = AuditEvent.objects.filter(action__startswith="product.")
    assert [a.action for a in audited] == ["product.clock_rollback_detected"]
    assert audited[0].object_id == activation_id


def test_signature_must_be_of_the_named_activation(activation_id: str, licensed: Any) -> None:
    key = Ed25519PrivateKey.generate()
    other = activate(request_body(key, instance_id=str(licensed.id)), key)
    other_id = other.json()["activation_id"]
    body = {"activation_id": other_id, "events": [event(1)]}
    response = signed_post(Client(), PATH, body, dev_device_key(), activation_id)
    assert (response.status_code, response.json()["code"]) == (401, "signature_invalid")
    stranger = send(activation_id, [event(1)], Ed25519PrivateKey.generate())
    assert stranger.json()["code"] == "signature_invalid"


def test_too_many_or_broken_events(activation_id: str) -> None:
    assert send(activation_id, [event(n) for n in range(101)]).status_code == 400
    assert send(activation_id, [{"id": "x", "type": "t"}]).json()["code"] == "invalid_request"
