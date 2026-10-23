"""keytool results on the dev keys equal contracts/vectors (E00-04)."""

from typing import Any

import pytest

from almi_keytool.certs import issue_certificate
from almi_keytool.encoding import b64url_decode
from almi_keytool.jws import LeaseContext, verify
from almi_keytool.rootkey import signing_key_from_seed

from .conftest import jws_vectors, vector_key

NOW = 1762071300
DAY = 86400


def chain_of(vector_name: str) -> list[str]:
    import json

    from almi_keytool.encoding import b64url_decode as d

    vector = next(v for v in jws_vectors() if v["name"] == vector_name)
    header = json.loads(d(vector["jws"].split(".")[0]))
    return list(header["chain"])


def test_issuer_certificate_equals_vector() -> None:
    root = signing_key_from_seed(b64url_decode(vector_key("dev-root.key")))
    certificate = issue_certificate(
        root,
        "dev-root",
        b64url_decode(vector_key("dev-issuer.pub")),
        role="issuer",
        kid="dev-issuer-1",
        iat=NOW - 30 * DAY,
        valid_days=760,
    )
    assert certificate == chain_of("01-valid-lease")[0]


def test_expired_issuer_certificate_equals_vector() -> None:
    root = signing_key_from_seed(b64url_decode(vector_key("dev-root.key")))
    certificate = issue_certificate(
        root,
        "dev-root",
        b64url_decode(vector_key("dev-issuer.pub")),
        role="issuer",
        kid="dev-issuer-0",
        iat=NOW - 760 * DAY,
        valid_days=759,
    )
    assert certificate == chain_of("06-expired-issuer-certificate")[0]


def test_local_server_certificate_equals_vector() -> None:
    issuer = signing_key_from_seed(b64url_decode(vector_key("dev-issuer.key")))
    certificate = issue_certificate(
        issuer,
        "dev-issuer-1",
        b64url_decode(vector_key("dev-local-server.pub")),
        role="local_server",
        kid="srv_01JAB3K9M2N4P6Q8R0S2T4V6W8-1",
        iat=NOW - DAY,
        valid_days=366,
        scope={
            "server_id": "srv_01JAB3K9M2N4P6Q8R0S2T4V6W8",
            "customer_id": "c3a1b2c3-d4e5-4f60-8a9b-0c1d2e3f4a5b",
            "products": ["alteroffice-desktop"],
            "quotas": {"6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60": 250},
        },
    )
    assert certificate == chain_of("02-valid-local-server-lease")[0]


@pytest.mark.parametrize("vector", jws_vectors(), ids=lambda v: v["name"])
def test_verify_gives_the_expected_result(vector: dict[str, Any]) -> None:
    roots = {r["kid"]: b64url_decode(r["pub"]) for r in vector["trust_roots"]}
    context = vector["context"]
    result = verify(
        vector["jws"],
        roots,
        now=vector["now"],
        revoked=set(context["revoked_kids"]),
        expected_typ="alm-lease+jws",
        lease=LeaseContext(
            product_code=context["product_code"],
            instance_id=context["instance_id"],
            device_key_thumbprint=context["device_key_thumbprint"],
            stored_seq=context["stored_seq"],
        ),
    )
    assert (result.valid, result.error, result.claims) == (
        vector["expected"]["valid"],
        vector["expected"]["error"],
        vector["expected"]["claims"],
    )
