"""E10-04: the audit journal with filters and CSV; a customer viewer sees its objects only."""

import csv
import io
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest

from apps.audit.domain import record
from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def events(licensed: Any, clock: FrozenClock) -> Any:
    lic = str(licensed.id)
    record("user:ivanova", "license.suspended", "license", lic, at=clock.now(), data={"r": "x"})
    record("user:petrov", "license.resumed", "license", lic, at=clock.now() + timedelta(days=1))
    record("system", "activation.released_auto", "activation", "act_1", at=clock.now())
    record("user:petrov", "iam.blocked", "user", "sidorov", at=clock.now() + timedelta(days=2))
    record("=cmd", "license.suspended", "license", "other", at=clock.now(), data={})
    return licensed


def test_filters(events: Any, clock: FrozenClock) -> None:
    console = sign_in("operator", clock)
    every = console.get("/api/admin/audit").json()
    assert every["count"] >= 5
    assert every["results"][0]["seq"] > every["results"][-1]["seq"]  # newest first

    def actions(**query: Any) -> list[str]:
        body = console.get("/api/admin/audit", query).json()
        return [e["action"] for e in body["results"]]

    assert actions(object_type="license", object_id=str(events.id)) == [
        "license.resumed",
        "license.suspended",
    ]
    assert actions(actor="petrov") == ["iam.blocked", "license.resumed"]
    assert set(actions(action="license.")) == {"license.suspended", "license.resumed"}
    since = (clock.now() + timedelta(hours=12)).isoformat()
    until = (clock.now() + timedelta(days=1, hours=12)).isoformat()
    assert actions(since=since, until=until) == ["license.resumed"]
    page = console.get("/api/admin/audit", {"page_size": 2, "page": 2}).json()
    assert len(page["results"]) == 2
    assert console.get("/api/admin/audit", {"page_size": 500}).status_code == 400


def test_csv_export(events: Any, clock: FrozenClock) -> None:
    console = sign_in("operator", clock)
    response = console.get("/api/admin/audit/export", {"action": "license."})
    assert response["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
    assert rows[0] == ["seq", "at", "actor", "action", "object_type", "object_id", "ip", "data"]
    assert {r[3] for r in rows[1:]} == {"license.suspended", "license.resumed"}
    assert all(r[1].endswith("Z") for r in rows[1:])
    # A value that a spreadsheet would run as a formula is quoted.
    assert "'=cmd" in [r[2] for r in rows[1:]]


def test_customer_viewer_sees_its_objects(
    events: Any, make_activation: Any, clock: FrozenClock
) -> None:
    from apps.iam.domain import create_account
    from tests.api_admin.session import PASSWORD

    activation = make_activation()
    record(
        "system", "activation.released_auto", "activation", activation.external_id, at=clock.now()
    )
    create_account(
        "client", PASSWORD, "customer_viewer", now=clock.now(), customer_id=events.customer_id
    )
    from django.test import Client

    client = Client()
    assert (
        client.post(
            "/api/admin/session",
            {"username": "client", "password": PASSWORD},
            content_type="application/json",
        ).status_code
        == 200
    )
    body = client.get("/api/admin/audit").json()
    objects = {(e["object_type"], e["object_id"]) for e in body["results"]}
    assert objects == {("license", str(events.id)), ("activation", activation.external_id)}
    rows = client.get("/api/admin/audit/export").content.decode().splitlines()
    assert len(rows) == 1 + body["count"]
