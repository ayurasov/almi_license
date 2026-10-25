"""POST /api/v1/activations/{activation_id}/check (E03-04, E03-07; section 5.3 of document 2).

Outside the apps package: the test checks tables of several modules (activation, audit, stats).
"""

from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import Client

from infra.clock import FrozenClock, use_clock
from tests.api_product.test_activate import FP, activate, claims_of, code_of, request_body
from tests.contract import openapi_errors, schema_errors
from tests.signed import dev_device_key, signed_post

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def activation_id(licensed: Any, issuer: Any) -> str:
    response = activate(request_body())
    assert response.status_code == 201
    value: str = response.json()["activation_id"]
    return value


def check_body(lease_seq: int = 1, **fields: Any) -> dict[str, Any]:
    return {
        "lease_seq": lease_seq,
        "product": {"code": "alteroffice-desktop", "version": "3.3.0", "build": "3.3.0.12"},
        "instance": {
            "os": {
                "family": "windows",
                "name": "Windows 11 Pro",
                "version": "10.1",
                "arch": "x86_64",
            }
        },
        "fingerprint": {"scheme": "fp-v1", "components": FP},
        "state": "ACTIVE",
        "usage": {"named_users": 1, "documents_opened": 12},
        "client_time": "2026-11-03T08:14:58Z",
    } | fields


def check(
    activation_id: str,
    document: dict[str, Any],
    signer: Ed25519PrivateKey | None = None,
    keyid: str | None = None,
) -> Any:
    return signed_post(
        Client(),
        f"/api/v1/activations/{activation_id}/check",
        document,
        signer or dev_device_key(),
        keyid or activation_id,
    )


def test_check_renews_the_lease(activation_id: str, server_clock: FrozenClock) -> None:
    from datetime import timedelta

    from apps.activation.models import Activation
    from apps.stats.models import UsageRecord

    server_clock.advance(timedelta(days=1))

    response = check(activation_id, check_body())

    assert response.status_code == 200, response.content
    body = response.json()
    assert openapi_errors("LeaseResponse", body) == []
    claims = claims_of(body["lease"])
    assert schema_errors("lease", claims) == []
    assert claims["seq"] == 2 and claims["sub"] == activation_id
    assert body["server_time"] == "2026-11-03T08:15:00Z"
    activation = Activation.objects.get(external_id=activation_id)
    assert activation.product_version == "3.3.0" and activation.os["version"] == "10.1"
    assert activation.last_seen_at == server_clock.now()
    assert activation.lease_seq == 2 and activation.lease.seq == 2
    usage = UsageRecord.objects.get()
    assert usage.activation_id == activation_id and usage.at == server_clock.now()
    assert usage.usage == {"named_users": 1, "documents_opened": 12}


def test_fingerprint_is_optional(activation_id: str) -> None:
    body = check_body()
    del body["fingerprint"]
    assert check(activation_id, body).status_code == 200


def test_fingerprint_out_of_tolerance(activation_id: str) -> None:
    other = {"disk": "a", "board": "b", "cpu": "c", "mac": "s9V"}

    response = check(
        activation_id, check_body(fingerprint={"scheme": "fp-v1", "components": other})
    )

    assert response.status_code == 412 and code_of(response) == "rebind_required"


def test_fingerprint_within_tolerance(activation_id: str) -> None:
    near = FP | {"mac": "new"}
    assert (
        check(
            activation_id, check_body(fingerprint={"scheme": "fp-v1", "components": near})
        ).status_code
        == 200
    )


@pytest.mark.parametrize("status", ["released", "released_auto"])
def test_released_activation(activation_id: str, status: str) -> None:
    from apps.activation.models import Activation

    Activation.objects.filter(external_id=activation_id).update(status=status)

    response = check(activation_id, check_body())

    assert response.status_code == 410 and code_of(response) == "activation_released"


@pytest.mark.parametrize("revoke", ["license", "activation"])
def test_revoked_answers_with_a_revoked_lease(
    activation_id: str, licensed: Any, revoke: str
) -> None:
    from apps.activation.models import Activation

    if revoke == "license":
        licensed.status = "revoked"
        licensed.save()
    else:
        Activation.objects.filter(external_id=activation_id).update(status="revoked")

    response = check(activation_id, check_body())

    assert response.status_code == 403 and code_of(response) == "license_revoked"
    lease = response.json()["data"]["lease"]
    claims = claims_of(lease)
    assert claims["lic"]["status"] == "revoked" and claims["seq"] == 2
    assert schema_errors("lease", claims) == []


def test_client_seq_ahead_of_the_server_is_an_anomaly(activation_id: str) -> None:
    from apps.audit.models import AuditEvent

    response = check(activation_id, check_body(lease_seq=7))

    assert response.status_code == 200
    assert claims_of(response.json()["lease"])["seq"] == 8
    event = AuditEvent.objects.get(action="lease_seq_anomaly")
    assert event.object_id == activation_id
    assert event.data == {"client_seq": 7, "server_seq": 1}


def test_seq_always_grows(activation_id: str) -> None:
    seqs = [
        claims_of(check(activation_id, check_body(lease_seq=n)).json()["lease"])["seq"]
        for n in (1, 2, 3)
    ]
    assert seqs == [2, 3, 4]


def test_directives_queue_acked_and_unsupported(
    activation_id: str, server_clock: FrozenClock
) -> None:
    from datetime import timedelta

    from apps.activation.domain import queue_directive
    from apps.audit.models import AuditEvent

    queued = []
    items: list[tuple[str, dict[str, Any]]] = [
        ("refresh_now", {}),
        ("set_check_interval", {"hours": 6}),
        ("collect_diagnostics", {"scope": "basic"}),
    ]
    for kind, params in items:
        queued.append(queue_directive(activation_id, kind, params, now=server_clock.now()))
        server_clock.advance(timedelta(seconds=1))
    refresh, interval, diagnostics = queued

    first = check(activation_id, check_body()).json()
    assert [d["id"] for d in first["directives"]] == [refresh, interval, diagnostics]
    assert first["directives"][1] == {
        "id": interval,
        "type": "set_check_interval",
        "params": {"hours": 6},
    }
    assert openapi_errors("LeaseResponse", first) == []

    second = check(
        activation_id,
        check_body(
            lease_seq=2, acked_directives=[refresh, interval], unsupported_directives=[diagnostics]
        ),
    ).json()

    assert second["directives"] == []
    event = AuditEvent.objects.get(action="directive.unsupported")
    assert event.data == {"directive_id": diagnostics, "type": "collect_diagnostics"}


def test_profile_directives_are_sent_until_acked(activation_id: str, licensed: Any) -> None:
    from apps.catalog.models import PolicyProfile

    profile = PolicyProfile.objects.get()
    profile.params = profile.params | {
        "directives": [{"id": "dir_profile_trust", "type": "update_trust"}]
    }
    profile.save()

    first = check(activation_id, check_body()).json()
    second = check(
        activation_id, check_body(lease_seq=2, acked_directives=["dir_profile_trust"])
    ).json()
    third = check(activation_id, check_body(lease_seq=3)).json()

    assert [d["id"] for d in first["directives"]] == ["dir_profile_trust"]
    assert second["directives"] == [] and third["directives"] == []


def test_messages_follow_the_state(
    activation_id: str, licensed: Any, server_clock: FrozenClock
) -> None:
    from datetime import timedelta

    server_clock.set(licensed.valid_until - timedelta(days=3))

    body = check(activation_id, check_body()).json()

    assert [m["id"] for m in body["messages"]] == ["notice.banner", "notice.7days"]
    notice = body["messages"][0]
    assert notice["state"] == "NOTICE" and notice["placement"] == "banner"
    assert notice["text"]["ru"] == "Лицензия действует до {valid_until}. Осталось {days_left}."
    lease_messages = claims_of(body["lease"])["messages"]
    assert {m["id"] for m in lease_messages} >= {
        "notice.banner",
        "grace.banner",
        "blocked.read_only",
    }
    assert openapi_errors("LeaseResponse", body) == []


def test_profile_overrides_a_message_text(
    activation_id: str, licensed: Any, server_clock: FrozenClock
) -> None:
    from datetime import timedelta

    from apps.catalog.models import PolicyProfile

    profile = PolicyProfile.objects.get()
    profile.params = profile.params | {
        "messages": {"notice.banner": {"text": {"ru": "Продлите лицензию до {valid_until}."}}}
    }
    profile.save()
    server_clock.set(licensed.valid_until - timedelta(days=20))

    body = check(activation_id, check_body()).json()

    assert body["messages"][0]["text"] == {"ru": "Продлите лицензию до {valid_until}."}
    assert body["messages"][0]["severity"] == "info"


def test_keyid_must_be_the_checked_activation(activation_id: str, licensed: Any) -> None:
    other = activate(request_body(instance_id="00000000-0000-4000-8000-000000000001")).json()

    response = check(activation_id, check_body(), keyid=other["activation_id"])

    assert response.status_code == 401 and code_of(response) == "signature_invalid"


def test_signature_by_another_key(activation_id: str) -> None:
    response = check(activation_id, check_body(), signer=Ed25519PrivateKey.generate())

    assert response.status_code == 401 and code_of(response) == "signature_invalid"


@pytest.mark.parametrize(
    "broken",
    [
        {"lease_seq": -1},
        {"state": "HAPPY"},
        {"product": {"code": "alteroffice-desktop"}},
        {"client_time": "now"},
    ],
)
def test_invalid_request(activation_id: str, broken: dict[str, Any]) -> None:
    response = check(activation_id, check_body() | broken)

    assert response.status_code == 400 and code_of(response) == "invalid_request"
