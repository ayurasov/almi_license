"""Shared fixtures. This file is outside the apps package, so it may build objects of several
modules for tests; module code itself crosses boundaries only through <module>.domain."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from infra.clock import FrozenClock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from apps.activation.models import Activation
    from apps.catalog.models import Product
    from apps.licensing.models import License

NOW = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture
def product(db: None, clock: FrozenClock) -> "Product":
    from apps.catalog.models import Metric, Product

    metric = Metric.objects.create(code="device", name={"ru": "Устройство"})
    return Product.objects.create(
        code="alteroffice-desktop",
        name={"ru": "АльтерОфис Desktop"},
        default_metric=metric,
        subject_type="device",
        created_at=clock.now(),
    )


@pytest.fixture
def license_(product: "Product", clock: FrozenClock) -> "License":
    from apps.licensing.models import Customer, License

    customer = Customer.objects.create(
        name="ООО «Пример»", inn="7701234560", created_at=clock.now()
    )
    return License.objects.create(
        customer=customer,
        product=product,
        metric=product.default_metric,
        type="subscription",
        limit=10,
        valid_from=clock.now(),
        status="active",
        created_at=clock.now(),
        updated_at=clock.now(),
    )


@pytest.fixture
def make_activation(license_: "License", clock: FrozenClock) -> "Callable[..., Activation]":
    """Create an active activation of license_; fields can be overridden."""
    from apps.activation.models import Activation

    def make(**fields: object) -> Activation:
        values: dict[str, object] = {
            "external_id": "act_01JABF8Q4W2N8C1R7ZB0Y5K6M3",
            "license": license_,
            "instance_id": "8d6a1f9e-6c39-4e57-9a3e-0e5d0f7b2c11",
            "subject_type": "device",
            "fp_components": {"scheme": "fp-v1", "components": {}},
            "device_pubkey": "",
            "product_version": "1.0",
            "os": {},
            "activated_at": clock.now(),
            "last_seen_at": clock.now(),
            "created_at": clock.now(),
        }
        return Activation.objects.create(**(values | fields))

    return make


LICENSE_KEY = "2645-7KQ9-MX2D-81ZT"
CAPABILITIES = ["view", "edit", "save", "create", "export", "print", "updates", "support", "macros"]
POLICY = {
    "enforcement": "enforce",
    "notify_before_days": 30,
    "grace_days": 14,
    "expiry_action": "restrict",
    "restricted_caps": ["updates", "macros"],
    "restricted_days": None,
    "hard_block_mode": "read_only",
    "read_only_caps": ["view", "print", "export"],
    "offline_grace_days": None,
    "check_interval_hours": 24,
    "release_after_days": 30,
    "reserve_pct": 3,
}


@pytest.fixture
def licensed(license_: "License", clock: FrozenClock) -> "License":
    """license_ with an edition, capabilities, a policy profile and the key LICENSE_KEY."""
    from apps.catalog.models import Capability, Edition, PolicyProfile
    from apps.licensing.domain import key_hash
    from apps.licensing.models import LicenseKey

    product = license_.product
    edition = Edition.objects.create(product=product, code="standard", name={"ru": "Стандарт"})
    edition.base_capabilities.set(
        [Capability.objects.create(product=product, code=code) for code in CAPABILITIES]
    )
    PolicyProfile.objects.create(
        code="alteroffice-desktop.commercial", version=3, params=POLICY, created_at=clock.now()
    )
    product.default_profile_code = "alteroffice-desktop.commercial"
    product.save()
    license_.edition = edition
    license_.valid_until = datetime(2027, 10, 31, 20, 59, 59, tzinfo=UTC)
    license_.support_until = license_.valid_until
    license_.save()
    LicenseKey.objects.create(
        license=license_,
        key_hash=key_hash(LICENSE_KEY),
        key_mask="2645-****-****-81ZT",
        format="v1",
    )
    return license_


@pytest.fixture
def issuer() -> "Iterator[object]":
    """The dev issuer key installed as the signing provider (deploy/dev)."""
    from apps.signing.domain import install_provider
    from infra.crypto.ed25519 import Ed25519Provider
    from tests.vectors import DEV_ISSUER_CERT, key_path

    provider = Ed25519Provider.from_files(key_path("dev-issuer.key"), DEV_ISSUER_CERT)
    install_provider(provider)
    yield provider
    install_provider(None)
