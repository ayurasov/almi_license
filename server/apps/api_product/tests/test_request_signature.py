"""ALMI-Signature request authentication (E05-01, section 4.4 of document 2).

Reference vectors contracts/vectors/request-signature, nonce replay, a changed body byte,
keyid "device" for activation, problem+json errors.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.api_product.auth import DeviceSignatureAuthentication, SignedRequest
from apps.api_product.domain.signature import NONCE_WINDOW, purge_nonces
from infra.clock import FrozenClock, use_clock
from infra.crypto.encoding import b64url_decode, b64url_encode
from infra.request_signing import body_digest, signing_string
from tests.vectors import VECTORS, key_path

ACTIVATION_ID = "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3"


class Echo(APIView):
    authentication_classes = [DeviceSignatureAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"keyid": cast(SignedRequest, request.auth).keyid})

    def post(self, request: Request) -> Response:
        return Response({"keyid": cast(SignedRequest, request.auth).keyid, "body": request.data})


class Activate(Echo):
    signature_allows_device_key = True


def vectors() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((VECTORS / "request-signature").glob("*.json"))
    ]


def at(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, UTC)


@pytest.fixture
def clock() -> Any:
    frozen = FrozenClock(at(1762071300))
    with use_clock(frozen):
        yield frozen


@pytest.fixture
def activation(make_activation: Any, clock: FrozenClock) -> Any:
    return make_activation(external_id=ACTIVATION_ID, device_pubkey=vectors()[0]["public_key"])


def device_key() -> Ed25519PrivateKey:
    seed = b64url_decode(key_path("dev-device.key").read_text(encoding="ascii").strip())
    return Ed25519PrivateKey.from_private_bytes(seed)


def header(keyid: str, created: int, nonce: str, method: str, path: str, body: bytes) -> str:
    text = signing_string(method, path, created, nonce, body)
    sig = b64url_encode(device_key().sign(text))
    return f'keyid="{keyid}", alg="ed25519", created={created}, nonce="{nonce}", sig="{sig}"'


def send(
    method: str, path: str, body: bytes, signature: str | None, view: type[APIView] = Echo
) -> Response:
    factory = APIRequestFactory()
    if method == "GET":
        request = factory.get(path)
    else:
        # The factory encodes the text as UTF-8: the bytes on the wire are body.
        request = factory.generic(method, path, body.decode("utf-8"), "application/json")
    if signature is not None:
        request.META["HTTP_ALMI_SIGNATURE"] = signature
    response: Response = view.as_view()(request)
    response.render()
    return response


def problem(response: Response) -> dict[str, Any]:
    assert response["Content-Type"] == "application/problem+json"
    body: dict[str, Any] = json.loads(response.content)
    assert body["status"] == response.status_code
    assert body["type"] == f"https://license.alter-os.ru/problems/{body['code']}"
    assert body["title"] and body["request_id"]
    return body


@pytest.mark.parametrize("vector", vectors(), ids=lambda v: v["name"])
def test_signing_string_and_digest(vector: dict[str, Any]) -> None:
    signed, body = vector["signed"], vector["request"]["body"].encode("utf-8")

    assert body_digest(body) == vector["expected"]["body_sha256"]
    assert signing_string(
        vector["request"]["method"], signed["path"], signed["created"], signed["nonce"], body
    ) == vector["expected"]["signing_string"].encode("utf-8")


@pytest.mark.django_db
@pytest.mark.parametrize("vector", vectors(), ids=lambda v: v["name"])
def test_vector(vector: dict[str, Any], activation: Any, clock: FrozenClock) -> None:
    clock.set(at(vector["server_now"]))
    request = vector["request"]

    response = send(
        request["method"],
        request["path"],
        request["body"].encode("utf-8"),
        vector["expected"]["header"],
    )

    if vector["expected"]["valid"]:
        assert response.status_code == 200, response.content
        assert response.data["keyid"] == ACTIVATION_ID
    else:
        assert response.status_code == 401
        body = problem(response)
        assert body["code"] == vector["expected"]["error"]
        if body["code"] == "clock_skew":
            assert datetime.fromisoformat(body["server_time"]) == at(vector["server_now"])
        assert response["WWW-Authenticate"] == "ALMI-Signature"


@pytest.mark.django_db
def test_nonce_replay_is_refused(activation: Any) -> None:
    vector = vectors()[1]
    request = vector["request"]
    args = (request["method"], request["path"], request["body"].encode("utf-8"))

    assert send(*args, vector["expected"]["header"]).status_code == 200
    replay = send(*args, vector["expected"]["header"])

    assert replay.status_code == 401
    assert problem(replay)["code"] == "signature_invalid"


@pytest.mark.django_db
def test_same_nonce_of_another_key_is_independent(activation: Any, clock: FrozenClock) -> None:
    created = int(clock.now().timestamp())
    signature = header(
        ACTIVATION_ID, created, "AAAAAAAAAAAAAAAAAAAAAA", "GET", "/api/v1/trust", b""
    )
    assert send("GET", "/api/v1/trust", b"", signature).status_code == 200

    body = json.dumps({"device_pubkey": b64url_encode(device_public())}).encode()
    signature = header("device", created, "AAAAAAAAAAAAAAAAAAAAAA", "POST", "/a", body)
    assert send("POST", "/a", body, signature, Activate).status_code == 200


@pytest.mark.django_db
def test_one_changed_body_byte_breaks_the_signature(activation: Any) -> None:
    vector = vectors()[1]
    request = vector["request"]
    body = request["body"].encode("utf-8")
    tampered = body.replace(b"17", b"18")
    assert tampered != body and len(tampered) == len(body)

    response = send(request["method"], request["path"], tampered, vector["expected"]["header"])

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("offset", "accepted"), [(-300, True), (300, True), (-301, False), (301, False)]
)
def test_clock_window(activation: Any, clock: FrozenClock, offset: int, accepted: bool) -> None:
    created = int(clock.now().timestamp()) + offset
    signature = header(
        ACTIVATION_ID, created, "q2p8q2p8q2p8q2p8q2p8qw", "GET", "/api/v1/trust", b""
    )

    response = send("GET", "/api/v1/trust", b"", signature)

    assert (response.status_code == 200) == accepted
    if not accepted:
        assert problem(response)["code"] == "clock_skew"


def device_public() -> bytes:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    return device_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


@pytest.mark.django_db
def test_activation_is_signed_with_the_key_from_the_body(clock: FrozenClock) -> None:
    body = json.dumps({"key": "X", "device_pubkey": b64url_encode(device_public())}).encode()
    created = int(clock.now().timestamp())
    signature = header(
        "device", created, "f93xQNtDa76y3xsWeyyv5Q", "POST", "/api/v1/activations", body
    )

    response = send("POST", "/api/v1/activations", body, signature, Activate)

    assert response.status_code == 200, response.content
    assert response.data["keyid"] == "device"


@pytest.mark.django_db
def test_device_keyid_needs_matching_body_key(clock: FrozenClock) -> None:
    other = b64url_encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw())
    body = json.dumps({"device_pubkey": other}).encode()
    created = int(clock.now().timestamp())
    signature = header(
        "device", created, "f93xQNtDa76y3xsWeyyv5Q", "POST", "/api/v1/activations", body
    )

    response = send("POST", "/api/v1/activations", body, signature, Activate)

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"


@pytest.mark.django_db
def test_device_keyid_is_only_for_activation(clock: FrozenClock) -> None:
    body = json.dumps({"device_pubkey": b64url_encode(device_public())}).encode()
    created = int(clock.now().timestamp())
    signature = header("device", created, "f93xQNtDa76y3xsWeyyv5Q", "POST", "/x", body)

    response = send("POST", "/x", body, signature)

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "signature",
    [
        None,
        "",
        'keyid="act_01JABF8Q4W2N8C1R7ZB0Y5K6M3"',
        'keyid="act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", alg="ed25519", created=1762071300, '
        'nonce="f93xQNtDa76y3xsWeyyv5Q", sig="AA", sig="AA"',
        'keyid="act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", alg="rsa", created=1762071300, '
        'nonce="f93xQNtDa76y3xsWeyyv5Q", sig="AA"',
        'keyid="act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", alg="ed25519", created="1762071300", '
        'nonce="f93xQNtDa76y3xsWeyyv5Q", sig="AA"',
        'keyid="act_01JABF8Q4W2N8C1R7ZB0Y5K6M3", alg="ed25519", created=1762071300, '
        'nonce="f93xQNtDa76y3xsWeyyv5Q", sig="not base64url!"',
    ],
)
def test_malformed_header_is_refused(activation: Any, signature: str | None) -> None:
    response = send("GET", "/api/v1/trust", b"", signature)

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"


@pytest.mark.django_db
def test_unknown_activation_is_refused(clock: FrozenClock) -> None:
    created = int(clock.now().timestamp())
    signature = header(
        ACTIVATION_ID, created, "f93xQNtDa76y3xsWeyyv5Q", "GET", "/api/v1/trust", b""
    )

    response = send("GET", "/api/v1/trust", b"", signature)

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"


@pytest.mark.django_db
def test_nonces_older_than_the_window_are_purged(activation: Any, clock: FrozenClock) -> None:
    from apps.api_product.models import RequestNonce

    vector = vectors()[0]
    assert (
        send("GET", vector["request"]["path"], b"", vector["expected"]["header"]).status_code == 200
    )
    assert RequestNonce.objects.count() == 1

    assert purge_nonces(clock.now() + NONCE_WINDOW) == 0
    assert purge_nonces(clock.now() + NONCE_WINDOW + timedelta(seconds=1)) == 1
    assert RequestNonce.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"device_pubkey": 1}', b"{}"])
def test_activation_body_without_a_device_key_is_refused(clock: FrozenClock, body: bytes) -> None:
    created = int(clock.now().timestamp())
    signature = header("device", created, "f93xQNtDa76y3xsWeyyv5Q", "POST", "/a", body)

    response = send("POST", "/a", body, signature, Activate)

    assert response.status_code == 401
    assert problem(response)["code"] == "signature_invalid"
