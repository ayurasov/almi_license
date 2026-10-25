"""Admin API: LK import wizard — upload, article mapping, confirmation (E06-01…E06-03, E07-07)."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from infra.clock import FrozenClock, use_clock
from tests.api_admin.session import Console, sign_in

pytestmark = pytest.mark.django_db
SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "lk-export-sample.xlsx"


@pytest.fixture(autouse=True)
def server_clock(clock: FrozenClock) -> Iterator[FrozenClock]:
    with use_clock(clock):
        yield clock


@pytest.fixture
def console(clock: FrozenClock) -> Console:
    return sign_in("operator", clock)


def upload(console: Console, content: bytes, name: str = "lk.xlsx") -> Any:
    return console.client.post(
        "/api/admin/imports",
        {"file": SimpleUploadedFile(name, content)},
        HTTP_X_CSRFTOKEN=console.token,
    )


def test_wizard_maps_articles_and_applies(console: Console, licensed: Any) -> None:
    from apps.catalog.models import Metric

    preview = upload(console, SAMPLE.read_bytes(), "../../lk-export.xlsx")
    assert preview.status_code == 201, preview.content
    body = preview.json()
    assert body["filename"] == "lk-export.xlsx"
    assert body["summary"]["new"] == 0  # no article is mapped yet
    assert "key_hash" not in body["rows"][0]
    assert "Артикул не сопоставлен: 01" in body["rows"][0]["errors"]

    mapping = {
        "product_id": str(licensed.product_id),
        "edition_id": str(licensed.edition_id),
        "metric_id": str(Metric.objects.get().id),
    }
    saved = console.client.put(
        "/api/admin/article-mappings/01",
        mapping,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=console.token,
    )
    assert saved.status_code == 200, saved.content
    assert [m["aa"] for m in console.get("/api/admin/article-mappings").json()] == ["01"]

    again = upload(console, SAMPLE.read_bytes()).json()
    assert again["summary"]["new"] > 0
    report = console.post(f"/api/admin/imports/{again['session_id']}/apply")
    assert report.status_code == 200, report.content
    assert report.json()["created"] == again["summary"]["new"]
    assert report.json()["customers_created"] == 0  # the customer of `licensed` has the INN
    assert console.post(f"/api/admin/imports/{again['session_id']}/apply").status_code == 400


def test_bad_file_and_bad_mapping(console: Console, licensed: Any) -> None:
    refused = upload(console, b"not a spreadsheet")
    assert refused.status_code == 400
    assert "file" in refused.json()["data"]["fields"]

    other = console.client.put(
        "/api/admin/article-mappings/0-1",
        {"product_id": str(licensed.product_id), "metric_id": str(licensed.metric_id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=console.token,
    )
    assert "aa" in other.json()["data"]["fields"]


def test_viewer_cannot_import(clock: FrozenClock) -> None:
    viewer = sign_in("customer_viewer", clock)
    assert upload(viewer, SAMPLE.read_bytes()).status_code == 403
    assert viewer.get("/api/admin/article-mappings").status_code == 403
