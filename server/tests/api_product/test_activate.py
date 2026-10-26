"""POST /api/v1/activations (E03-01, E03-02, E03-03; section 5.2 of document 2).

Outside the apps package: the test checks tables of several modules (activation, audit).
"""

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.test import Client

from conftest import LICENSE_KEY
from infra.clock import FrozenClock, use_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from tests.contract import openapi_errors, schema_errors
from tests.signed import dev_device_key, public_b64, signed_post

PATH = "/api/v1/activations"
INSTANCE = "8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c11"
FP = {"disk": "pX0", "board": "Zr4", "cpu": "k1Q", "mac": "s9V"}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


def request_body(
    key: Ed25519PrivateKey | None = None,
    *,
    license_key: str = LICENSE_KEY,
    instance_id: str = INSTANCE,
    fp: dict[str, str] | None = None,
    product: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "license_key": license_key,
        "product": {"code": "alteroffice-desktop", "version": "3.2.0"} | (product or {}),
        "instance": {
            "instance_id": instance_id,
            "subject_type": "device",
            "name": "WS-0451",
            "os": {
                "family": "windows",
                "name": "Windows 11 Pro",
                "version": "10.0",
                "arch": "x86_64",
            },
        },
        "fingerprint": {"scheme": "fp-v1", "components": fp or FP},
        "device_pubkey": public_b64(key or dev_device_key()),
        "client_time": "2026-11-02T08:14:58Z",
    }


def activate(document: dict[str, Any], key: Ed25519PrivateKey | None = None) -> Any:
    return signed_post(Client(), PATH, document, key or dev_device_key(), "device")


def claims_of(lease: str) -> dict[str, Any]:
    claims: dict[str, Any] = json.loads(b64url_decode(lease.split(".")[1]))
    return claims


def code_of(response: Any) -> str:
    assert response["Content-Type"] == "application/problem+json"
    assert openapi_errors("Problem", response.json()) == []
    code: str = response.json()["code"]
    return code


def test_new_activation(licensed: Any, issuer: Any, clock: FrozenClock) -> None:
    from apps.activation.models import Activation
    from apps.audit.models import AuditEvent

    response = activate(request_body())

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["activation_id"].startswith("act_") and body["status"] == "active"
    assert body["server_time"] == "2026-11-02T08:15:00Z"
    assert body["next_check_at"] == "2026-11-03T08:15:00Z"
    assert body["messages"] == [] and body["directives"] == []

    header, payload, signature = body["lease"].split(".")
    Ed25519PublicKey.from_public_bytes(issuer.public_key()).verify(
        b64url_decode(signature), f"{header}.{payload}".encode()
    )
    claims = claims_of(body["lease"])
    assert openapi_errors("LeaseResponse", body) == []
    assert schema_errors("lease", claims) == []
    now = int(clock.now().timestamp())
    thumbprint = b64url_encode(
        hashlib.sha256(
            ('{"crv":"Ed25519","kty":"OKP","x":"' + public_b64(dev_device_key()) + '"}').encode()
        ).digest()
    )
    assert claims == {
        "ver": 1,
        "iss": "https://license.alter-os.ru",
        "sub": body["activation_id"],
        "aud": "alteroffice-desktop",
        "iat": now,
        "nbf": now,
        "seq": 1,
        "lic": {
            "id": str(licensed.id),
            "type": "subscription",
            "status": "active",
            "edition": "standard",
            "valid_from": "2026-11-02T08:15:00Z",
            "valid_until": "2027-10-31T20:59:59Z",
            "support_until": "2027-10-31T20:59:59Z",
            "customer": {"id": str(licensed.customer_id), "name": "ООО «Пример»"},
        },
        "subject": {
            "type": "device",
            "instance_id": INSTANCE,
            "fp": {"scheme": "fp-v1", "components": FP},
            "device_key_thumbprint": thumbprint,
        },
        "limits": {},
        "capabilities": sorted(
            ["view", "edit", "save", "create", "export", "print", "updates", "support", "macros"]
        ),
        "policy": {
            "version": 3,
            "enforcement": "enforce",
            "notify_before_days": 30,
            "grace_days": 14,
            "expiry_action": "restrict",
            "restricted_caps": ["macros", "updates"],  # sorted: canonical lease
            "restricted_days": None,
            "hard_block_mode": "read_only",
            "read_only_caps": ["export", "print", "view"],
            "offline_grace_days": None,
            "check_interval_hours": 24,
            "release_after_days": 30,
        },
        "messages": claims["messages"],
        "server_time": now,
    }
    assert [m["id"] for m in claims["messages"]] == sorted(m["id"] for m in claims["messages"])
    assert {m["id"] for m in claims["messages"]} >= {"notice.banner", "revoked.dialog"}

    activation = Activation.objects.get(external_id=body["activation_id"])
    assert activation.status == "active" and not activation.in_reserve
    assert activation.lease_seq == 1 and activation.lease.seq == 1
    assert activation.lease.jws_hash == hashlib.sha256(body["lease"].encode()).hexdigest()
    assert activation.fp_components == {"scheme": "fp-v1", "components": FP}
    event = AuditEvent.objects.get(action="activation.created")
    assert event.object_id == body["activation_id"]
    assert LICENSE_KEY not in json.dumps(event.data)


def test_repeat_activation_takes_no_seat(licensed: Any, issuer: Any) -> None:
    from apps.activation.models import Activation

    first = activate(request_body()).json()
    second = activate(request_body())

    assert second.status_code == 200
    assert second.json()["activation_id"] == first["activation_id"]
    assert claims_of(second.json()["lease"])["seq"] == 2
    assert Activation.objects.count() == 1


def test_new_device_key_within_tolerance_replaces_the_key(licensed: Any, issuer: Any) -> None:
    from apps.activation.models import Activation

    first = activate(request_body()).json()
    new_key = Ed25519PrivateKey.generate()
    changed = FP | {"mac": "other"}

    response = activate(request_body(new_key, fp=changed), new_key)

    assert response.status_code == 200
    activation = Activation.objects.get(external_id=first["activation_id"])
    assert activation.device_pubkey == public_b64(new_key)
    assert activation.fp_components["components"] == changed


def test_rebind_with_the_same_key_updates_the_fingerprint(licensed: Any, issuer: Any) -> None:
    from apps.activation.models import Activation

    activate(request_body())
    changed = {"disk": "a", "board": "b", "cpu": "c", "mac": "d"}

    response = activate(request_body(fp=changed))

    assert response.status_code == 200
    assert Activation.objects.get().fp_components["components"] == changed


def test_cloned_instance_is_a_conflict(licensed: Any, issuer: Any) -> None:
    from apps.activation.models import Activation
    from apps.audit.models import AuditEvent

    activate(request_body())
    clone = Ed25519PrivateKey.generate()

    response = activate(
        request_body(clone, fp={"disk": "a", "board": "b", "cpu": "c", "mac": "d"}), clone
    )

    assert response.status_code == 409 and code_of(response) == "instance_conflict"
    assert response.json()["user_message"]["ru"].startswith("Этот компьютер похож на копию")
    assert Activation.objects.filter(status="conflict").count() == 1
    assert Activation.objects.filter(status="active").count() == 1
    assert AuditEvent.objects.filter(action="activation.conflict").count() == 1


@pytest.mark.parametrize("key", ["2645-7KQ9-MX2D", "2645_7KQ9_MX2D_81ZT", "26457KQ9MX2D81ZT", ""])
def test_malformed_key(licensed: Any, issuer: Any, key: str) -> None:
    response = activate(request_body(license_key=key))

    assert response.status_code == 400 and code_of(response) == "invalid_key_format"


def test_key_is_normalised(licensed: Any, issuer: Any) -> None:
    assert activate(request_body(license_key=" 2645-7kq9-mx2d-81zt\t")).status_code == 201


def test_unknown_key(licensed: Any, issuer: Any) -> None:
    response = activate(request_body(license_key="2645-AAAA-BBBB-CCCC"))

    assert response.status_code == 404 and code_of(response) == "key_not_found"


def test_revoked_license(licensed: Any, issuer: Any) -> None:
    licensed.status = "revoked"
    licensed.save()

    response = activate(request_body())

    assert response.status_code == 403 and code_of(response) == "license_revoked"


@pytest.mark.parametrize("presented", [{"code": "alteros"}, {"edition": "professional"}])
def test_other_product_or_edition(licensed: Any, issuer: Any, presented: dict[str, str]) -> None:
    response = activate(request_body(product=presented))

    assert response.status_code == 403 and code_of(response) == "product_mismatch"


def test_revoked_is_checked_before_product(licensed: Any, issuer: Any) -> None:
    licensed.status = "revoked"
    licensed.save()

    assert code_of(activate(request_body(product={"code": "alteros"}))) == "license_revoked"


@pytest.mark.parametrize(
    ("after_term", "enforcement", "status"),
    [
        (timedelta(days=14) - timedelta(seconds=1), "", 201),  # last second of grace
        (timedelta(days=14), "", 403),
        (timedelta(days=14), "monitor", 201),
    ],
)
def test_expired_license(
    licensed: Any,
    issuer: Any,
    server_clock: FrozenClock,
    after_term: timedelta,
    enforcement: str,
    status: int,
) -> None:
    licensed.enforcement = enforcement
    licensed.save()
    server_clock.set(licensed.valid_until + after_term)

    response = activate(request_body())

    assert response.status_code == status, response.content
    if status == 403:
        assert code_of(response) == "license_expired"


def test_seats_and_reserve(licensed: Any, issuer: Any) -> None:
    from apps.activation.models import Activation

    licensed.limit = 2
    licensed.reserve_pct = 50  # ceil(2 * 50 / 100) = 1 seat in reserve
    licensed.save()

    statuses = [
        activate(request_body(instance_id=f"00000000-0000-4000-8000-00000000000{n}")).status_code
        for n in range(3)
    ]
    exhausted = activate(request_body(instance_id="00000000-0000-4000-8000-000000000009"))

    assert statuses == [201, 201, 201]
    assert (
        list(
            Activation.objects.order_by("created_at", "external_id").values_list(
                "in_reserve", flat=True
            )
        ).count(True)
        == 1
    )
    assert exhausted.status_code == 409 and code_of(exhausted) == "seats_exhausted"
    problem = exhausted.json()
    assert problem["data"] == {"used": 3, "limit": 2, "reserve": 1}
    assert "(3 из 3)" in problem["user_message"]["ru"]


def test_reserve_pct_comes_from_the_profile(licensed: Any, issuer: Any) -> None:
    licensed.limit = 10  # profile reserve_pct = 3 -> ceil(0.3) = 1
    licensed.save()

    statuses = [
        activate(request_body(instance_id=f"00000000-0000-4000-8000-0000000000{n:02}")).status_code
        for n in range(12)
    ]

    assert statuses == [201] * 11 + [409]


def test_signature_must_be_by_the_device_key_in_the_body(licensed: Any, issuer: Any) -> None:
    other = Ed25519PrivateKey.generate()

    response = activate(request_body(), other)

    assert response.status_code == 401 and code_of(response) == "signature_invalid"


@pytest.mark.parametrize(
    "broken",
    [
        {"product": {"code": "alteroffice-desktop"}},
        {"instance": {"instance_id": "not-a-uuid", "subject_type": "device", "os": {}}},
        {"fingerprint": {"scheme": "fp-v2", "components": {}}},
        {"client_time": "yesterday"},
    ],
)
def test_invalid_request(licensed: Any, issuer: Any, broken: dict[str, Any]) -> None:
    response = activate(request_body() | broken)

    assert response.status_code == 400 and code_of(response) == "invalid_request"


# A fresh UUID per run: the value of the Idempotency-Key header.
REPEAT_ID = str(uuid.uuid4())


def test_idempotency_key_replays_the_first_response(licensed: Any, issuer: Any) -> None:
    from django.test import Client as _Client

    from apps.activation.models import Activation

    body = request_body()
    first = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, body, dev_device_key(), "device"
    )
    again = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, body, dev_device_key(), "device"
    )

    assert again.status_code == first.status_code == 201
    assert again.json() == first.json()
    assert Activation.objects.get().lease_seq == 1  # the repeat did not run the activation again


def test_idempotency_key_with_another_body_or_malformed(licensed: Any, issuer: Any) -> None:
    from django.test import Client as _Client

    signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID),
        PATH,
        request_body(),
        dev_device_key(),
        "device",
    )
    other = request_body() | {"client_time": "2026-11-02T08:15:59Z"}
    conflict = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, other, dev_device_key(), "device"
    )
    assert conflict.status_code == 409 and code_of(conflict) == "idempotency_conflict"
    bad = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY="k1"), PATH, request_body(), dev_device_key(), "device"
    )
    assert bad.status_code == 400 and code_of(bad) == "invalid_request"


def test_idempotent_error_is_replayed_and_window_ends(
    licensed: Any, issuer: Any, clock: FrozenClock
) -> None:
    from django.test import Client as _Client

    body = request_body(product={"code": "alteros"})
    first = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, body, dev_device_key(), "device"
    )
    again = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, body, dev_device_key(), "device"
    )
    assert first.status_code == again.status_code == 403
    assert again["Content-Type"] == "application/problem+json"
    clock.advance(timedelta(hours=25))
    later = request_body(product={"code": "alteros"}) | {"client_time": "2026-11-03T09:15:00Z"}
    fresh = signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, later, dev_device_key(), "device"
    )
    assert fresh.status_code == 403


def test_times_are_utc(licensed: Any, issuer: Any) -> None:
    body = activate(request_body()).json()
    assert datetime.fromisoformat(body["server_time"]).tzinfo == UTC


def test_issued_activation_lease_for_cross_verification(
    licensed: Any, issuer: Any, clock: FrozenClock, tmp_path: Any
) -> None:
    """make cross-verify: the lease of a real activation passes almi-keytool and LeaseVerifier."""
    import os
    from pathlib import Path

    from tests.vectors import jws_vector

    body = activate(request_body()).json()
    claims = claims_of(body["lease"])
    vector = {
        "name": "issued-activation-lease",
        "description": "Lease of POST /api/v1/activations (E03-01 cross-check)",
        "jws": body["lease"],
        "trust_roots": jws_vector("01-valid-lease")["trust_roots"],
        "now": int(clock.now().timestamp()),
        "context": {
            "product_code": "alteroffice-desktop",
            "instance_id": INSTANCE,
            "device_key_thumbprint": claims["subject"]["device_key_thumbprint"],
            "stored_seq": 0,
            "revoked_kids": [],
        },
        "expected": {"valid": True, "error": None, "claims": claims},
    }
    directory = Path(os.environ.get("ALMI_ISSUED_VECTORS_DIR") or tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "issued-activation-lease.json").write_text(
        json.dumps(vector, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_stored_responses_are_purged_by_the_hourly_task(
    licensed: Any, issuer: Any, clock: FrozenClock
) -> None:
    from django.test import Client as _Client

    from apps.api_product.models import IdempotencyRecord
    from apps.outbox.domain import enqueue, run_due

    signed_post(
        _Client(HTTP_IDEMPOTENCY_KEY=REPEAT_ID), PATH, request_body(), dev_device_key(), "device"
    )
    assert IdempotencyRecord.objects.count() == 1
    enqueue("api_product.idempotency_purge", {}, now=clock.now())
    run_due(now=clock.now())
    assert IdempotencyRecord.objects.count() == 1  # still within 24 h
    later = clock.now() + timedelta(hours=25)
    enqueue("api_product.idempotency_purge", {}, now=later)
    run_due(now=later)
    assert IdempotencyRecord.objects.count() == 0


def test_requests_without_idempotency_key_are_counted(licensed: Any, issuer: Any) -> None:
    """Accepted, but counted for /metrics (question 37)."""
    from django.test import Client as _Client

    from infra import metrics

    metrics.reset()
    assert activate(request_body()).status_code == 201
    with_key = _Client(HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert signed_post(with_key, PATH, request_body(), dev_device_key(), "device").status_code in {
        200,
        201,
    }
    text = metrics.render()
    assert 'almi_product_requests_without_idempotency_key_total{operation="Activate"} 1.0' in text
