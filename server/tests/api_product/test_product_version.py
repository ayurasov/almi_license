"""422 unsupported_product_version (section 16 of document 2): a licence may name the highest
version of the product it covers ("3" — every 3.x, "3.2" — every 3.2.x); a newer one is refused
at activation. An empty limit covers every version."""

from typing import Any

import pytest

from apps.licensing.domain import update_settings, version_supported
from infra.clock import FrozenClock
from infra.errors import DomainError
from tests.api_product.test_activate import activate, code_of, request_body

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("version", "limit", "supported"),
    [
        ("3.2.0", "", True),
        ("3.2.0", "3", True),
        ("3.9.17", "3", True),
        ("4.0.0", "3", False),
        ("3.2.5", "3.2", True),
        ("3.3.0", "3.2", False),
        ("2.8", "3.2", True),
        ("3.2.0-beta.1", "3.2", True),
        ("10.0", "9", False),
        ("lm-demo", "3", False),  # not a version: refused when a limit is set
        ("lm-demo", "", True),
    ],
)
def test_version_supported(version: str, limit: str, supported: bool) -> None:
    assert version_supported(version, limit) is supported


def test_newer_version_is_refused_with_422(licensed: Any, issuer: Any, clock: FrozenClock) -> None:
    update_settings(licensed.id, {"max_product_version": "3"}, actor="user:op", now=clock.now())
    newer = activate(request_body(product={"version": "4.0.1"}))
    assert newer.status_code == 422
    assert code_of(newer) == "unsupported_product_version"
    assert activate(request_body(product={"version": "3.2.0"})).status_code == 201


def test_limit_format_is_checked(licensed: Any, clock: FrozenClock) -> None:
    with pytest.raises(DomainError) as error:
        update_settings(licensed.id, {"max_product_version": "3.x"}, actor="a", now=clock.now())
    assert "max_product_version" in (error.value.data or {})["fields"]
    lic = update_settings(licensed.id, {"max_product_version": ""}, actor="a", now=clock.now())
    assert lic.max_product_version == ""
