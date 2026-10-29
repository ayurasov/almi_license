"""E11-03: /api/activate/ of registration.sh (section 12.1 of document 2)."""

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client

from apps.compat.domain import os_node_id
from conftest import LICENSE_KEY
from infra.clock import FrozenClock, use_clock

FIXTURES = Path(__file__).parent / "registration"
PATH = "/api/activate/"
NOW = datetime(2026, 11, 2, 8, 15, tzinfo=UTC)
MACHINE = "0f343b0931126a20f133d67c2b018a3b"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.skip = tag in ("title", "script", "style")

    def handle_endtag(self, tag: str) -> None:
        self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def page_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    return type(value).__name__


def fixture(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return document


@pytest.fixture
def clock() -> Iterator[FrozenClock]:
    frozen = FrozenClock(NOW)
    with use_clock(frozen):
        yield frozen


@pytest.fixture
def alteros(db: None, clock: FrozenClock, issuer: Any) -> Any:
    from apps.catalog.models import Edition, Metric, Product
    from apps.licensing.domain import key_hash
    from apps.licensing.models import Customer, License, LicenseKey

    call_command("loadcatalog")
    product = Product.objects.get(code="alteros")
    customer = Customer.objects.create(name="ООО «Пример»", inn="7701234560", created_at=NOW)
    license_ = License.objects.create(
        customer=customer,
        product=product,
        edition=Edition.objects.get(product=product, code="workstation"),
        metric=Metric.objects.get(code="os_node"),
        type="subscription",
        limit=2,
        reserve_pct=0,
        valid_from=NOW,
        valid_until=datetime(2027, 10, 31, 20, 59, 59, tzinfo=UTC),
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    LicenseKey.objects.create(
        license=license_,
        key_hash=key_hash(LICENSE_KEY),
        key_mask="2645-****-****-81ZT",
        format="v1",
    )
    return license_


def send(case: dict[str, Any], ip: str = "198.51.100.7") -> Any:
    request = case["request"]
    client = Client(REMOTE_ADDR=ip)
    headers = {"HTTP_ACCEPT": request["accept"]} if "accept" in request else {}
    if request["method"] == "POST":
        form = {k: v.replace("{key}", LICENSE_KEY) for k, v in request["form"].items()}
        return client.post(PATH, form, **headers)
    query = {k: v.replace("{key}", LICENSE_KEY) for k, v in request["query"].items()}
    return client.get(PATH, query, **headers)


@pytest.mark.parametrize("name", sorted(p.stem for p in FIXTURES.glob("*.json")))
def test_fixtures(alteros: Any, name: str) -> None:
    case = fixture(name)
    for earlier in case.get("before", []):
        assert send(fixture(earlier)).status_code == 200
    response = send(case)
    expected = case["response"]
    assert response.status_code == expected["status"]
    if "json" in expected:
        assert response["Content-Type"].startswith("application/json")
        assert shape(response.json()) == shape(expected["json"])
        assert response.json()["message"] == expected["json"]["message"]
    else:
        assert response["Content-Type"].startswith("text/html")
        assert page_text(response.content.decode()) == expected["text"]


def test_node_is_an_os_node_activation_and_repeat_takes_no_seat(alteros: Any) -> None:
    from apps.activation.models import Activation

    first = send(fixture("activated-json"))
    again = send(fixture("already-json"))  # same data in upper case, POST
    assert (first.json()["used"], again.json()["used"]) == (1, 1)
    activation = Activation.objects.get()
    assert activation.subject_type == "os_node"
    assert activation.instance_id == os_node_id(MACHINE)
    assert activation.instance_name == "ws-01"
    assert activation.fp_components["components"] == {"machine": MACHINE}


def test_key_of_another_product_is_not_found(alteros: Any) -> None:
    from apps.catalog.models import Product

    alteros.product = Product.objects.get(code="alteroffice-web")
    alteros.save()
    assert send(fixture("activated-json")).status_code == 404


def test_suspended_licence_is_not_registered(alteros: Any) -> None:
    alteros.status = "suspended"
    alteros.save()
    response = send(fixture("activated-json"))
    assert response.status_code == 404
    assert response.json()["message"] == "Лицензия не найдена или недействительна"


def test_expired_licence(alteros: Any, clock: FrozenClock) -> None:
    alteros.enforcement = "enforce"
    alteros.valid_from = NOW - timedelta(days=500)
    alteros.valid_until = NOW - timedelta(days=120)
    alteros.save()
    response = send(fixture("activated-json"))
    assert response.status_code == 403
    assert response.json()["message"] == "Срок действия лицензии истёк"


def test_limit_per_key(alteros: Any) -> None:
    case = fixture("activated-json")
    codes = [send(case, ip=f"198.51.100.{n}").status_code for n in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


def test_limit_per_ip(alteros: Any) -> None:
    case = fixture("not-found-json")
    codes = []
    for n in range(21):
        query = case["request"]["query"] | {"lic": f"9999-AAAA-BBBB-{n:04d}"}
        codes.append(Client(REMOTE_ADDR="203.0.113.5").get(PATH, query).status_code)
    # The 10th error blocks the IP before the limit of 20 an hour is reached.
    assert codes[:10] == [404] * 10
    assert set(codes[10:]) == {429}


def test_ip_is_blocked_for_900_seconds_after_10_errors(alteros: Any, clock: FrozenClock) -> None:
    bad = fixture("bad-request-html")
    for _ in range(10):
        assert send(bad, ip="203.0.113.9").status_code == 400
    blocked = send(fixture("activated-json"), ip="203.0.113.9")
    assert blocked.status_code == 429
    assert int(blocked["Retry-After"]) == 900
    assert blocked.json()["message"] == "Слишком много попыток, повторите позже"
    # The key itself is spent by the 10 requests (10 an hour per key); another key is used below.
    assert send(fixture("not-found-json"), ip="203.0.113.10").status_code == 404
    clock.advance(timedelta(seconds=900))
    assert send(fixture("not-found-json"), ip="203.0.113.9").status_code == 404
