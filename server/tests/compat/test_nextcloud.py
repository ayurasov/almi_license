"""E11-01, E11-02: subscription adapter of AlterOffice Web (section 11.1 of document 2)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client

from apps.compat.domain import server_instance_id
from conftest import LICENSE_KEY
from infra.clock import FrozenClock, use_clock

FIXTURES = Path(__file__).parent / "nextcloud"
KEY = LICENSE_KEY
PATH = f"/apps/zammad_organisation_management/api/query/subscription/{KEY}"
UNTIL = datetime(2027, 10, 31, 20, 59, 59, tzinfo=UTC)
NOW = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)


def fixture(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document


def shape(value: Any) -> Any:
    """Field names and value types, the part of an answer the support app depends on."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    return type(value).__name__


@pytest.fixture
def clock() -> Iterator[FrozenClock]:
    frozen = FrozenClock(NOW)
    with use_clock(frozen):
        yield frozen


@pytest.fixture
def web(db: None, clock: FrozenClock, issuer: Any) -> Any:
    from apps.catalog.models import Edition, Metric, Product
    from apps.licensing.domain import key_hash
    from apps.licensing.models import Customer, License, LicenseKey

    call_command("loadcatalog")
    product = Product.objects.get(code="alteroffice-web")
    customer = Customer.objects.create(name="ООО «Пример»", inn="7701234560", created_at=NOW)
    license_ = License.objects.create(
        customer=customer,
        product=product,
        edition=Edition.objects.get(product=product, code="enterprise"),
        metric=Metric.objects.get(code="server_instance"),
        type="subscription",
        limit=1,
        reserve_pct=0,
        valid_from=NOW,
        valid_until=UNTIL,
        support_until=UNTIL,
        enforcement="enforce",
        limits={"named_users": 500, "only_count_active": False},
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    LicenseKey.objects.create(
        license=license_, key_hash=key_hash(KEY), key_mask="2645-****-****-81ZT", format="v1"
    )
    return license_


def post(body: dict[str, Any], path: str = PATH) -> Any:
    return Client().post(path, body, content_type="application/json")


def test_answer_matches_the_fixture(web: Any) -> None:
    case = fixture("subscription-active.json")
    response = post(case["request"]["body"])
    assert response.status_code == case["response"]["status"]
    assert shape(response.json()) == shape(case["response"]["body"])
    assert response.json()["endDate"] == "2027-10-31"  # 23:59:59 in Moscow
    assert response.json()["amountOfUsers"] == 500
    assert response.json()["extendedSupport"] is True


def test_unknown_key_matches_the_fixture(web: Any) -> None:
    case = fixture("subscription-not-found.json")
    for key in ("2645-7KQ9-MX2D-0000", "not-a-key"):
        response = post(case["request"]["body"], PATH.replace(KEY, key))
        assert response.status_code == case["response"]["status"]
        assert response.json() == case["response"]["body"]


def test_key_of_another_product_is_not_found(web: Any) -> None:
    from apps.catalog.models import Product

    web.product = Product.objects.get(code="alteros")
    web.save()
    assert post(fixture("subscription-active.json")["request"]["body"]).status_code == 404


def test_instance_becomes_an_activation_and_counters_are_usage(web: Any) -> None:
    from apps.activation.models import Activation
    from apps.stats.models import UsageRecord

    body = fixture("subscription-active.json")["request"]["body"]
    post(body)
    post(body | {"userCount": 130})
    activation = Activation.objects.get()
    assert activation.subject_type == "server_instance"
    assert activation.instance_id == server_instance_id("oc8kz3m1vq2a")
    assert activation.product_version == "28.0.4.1"
    assert activation.lease_seq == 2  # activation, then a check
    counters = [r.usage for r in UsageRecord.objects.order_by("at", "id")]
    assert {c["named_users"] for c in counters} == {120, 130}
    assert counters[0]["active_users"] == 87
    assert counters[0]["apps"]["spreed"] == "18.0.7"


def test_second_instance_follows_the_seat_rules(web: Any) -> None:
    from apps.activation.models import Activation

    body = fixture("subscription-active.json")["request"]["body"]
    assert post(body).status_code == 200
    other = post(body | {"instanceId": "ocsecond0001"})
    # The app cannot show a refusal: it gets the subscription, no seat is taken.
    assert other.status_code == 200
    assert Activation.objects.filter(status="active").count() == 1
    web.limit = 2
    web.save()
    post(body | {"instanceId": "ocsecond0001"})
    assert Activation.objects.filter(status="active").count() == 2


@pytest.mark.parametrize(
    ("after", "users", "support"),
    [
        (timedelta(days=-60), 500, True),  # ACTIVE
        (timedelta(days=3), 500, False),  # GRACE
        (timedelta(days=20), 120, False),  # RESTRICTED: no new users
    ],
)
def test_states(web: Any, clock: FrozenClock, after: timedelta, users: int, support: bool) -> None:
    body = fixture("subscription-active.json")["request"]["body"]
    assert post(body).status_code == 200  # the instance is activated while the term runs
    clock.set(UNTIL + after)
    answer = post(body).json()
    assert answer["endDate"] == "2027-10-31"
    assert answer["amountOfUsers"] == users
    assert answer["extendedSupport"] is support


def test_account_manager_or_general_support(web: Any, settings: Any) -> None:
    settings.SUPPORT_CONTACT = {"name": "Поддержка", "email": "support@example.org", "phone": ""}
    body = fixture("subscription-active.json")["request"]["body"]
    assert post(body).json()["accountManagerInfo"] == settings.SUPPORT_CONTACT
    manager = {"name": "Иван Петров", "email": "ivan.petrov@example.org", "phone": "+7 495"}
    web.customer.contact = {"manager": manager}
    web.customer.save()
    assert post(body).json()["accountManagerInfo"] == manager


def test_only_active_users_and_perpetual(web: Any) -> None:
    web.limits = {"active_users": 300}
    web.type = "perpetual"
    web.valid_until = None
    web.save()
    answer = post(fixture("subscription-active.json")["request"]["body"]).json()
    assert answer["onlyCountActiveUsers"] is True
    assert answer["amountOfUsers"] == 300
    assert answer["endDate"] == "2027-10-31"  # support_until for a perpetual licence


def test_revoked_licence_is_not_found(web: Any) -> None:
    body = fixture("subscription-active.json")["request"]["body"]
    post(body)
    web.status = "revoked"
    web.save()
    assert post(body).status_code == 404


def test_rate_limit_per_key(web: Any) -> None:
    body = fixture("subscription-active.json")["request"]["body"]
    for _ in range(10):
        assert post(body).status_code == 200
    limited = post(body)
    assert limited.status_code == 429
    assert int(limited["Retry-After"]) > 0


def test_bad_requests(web: Any) -> None:
    assert post({"userCount": 1}).status_code == 400
    assert Client().get(PATH).status_code == 405
    form = Client().post(PATH, {"instanceId": "oc8kz3m1vq2a", "userCount": "5"})
    assert form.status_code == 200


def test_users_over_the_limit_are_seen_in_statistics(web: Any, clock: FrozenClock) -> None:
    from tests.api_admin.session import sign_in

    body = fixture("subscription-active.json")["request"]["body"]
    post(body)
    clock.advance(timedelta(hours=6))
    post(body | {"userCount": 520})  # the latest counters count
    console = sign_in("operator", clock)
    [row] = console.get("/api/admin/stats").json()["rows"]
    assert (row["users"], row["user_limit"], row["users_exceeded"]) == (520, 500, True)
    assert row["active"] == 1
