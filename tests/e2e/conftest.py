"""Fixtures of the end-to-end scenarios; the HTML report of their steps (E16-04)."""

import html
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from stand import Device, Stand, start_server

LM_DEMO = os.environ.get("LM_DEMO", "")
DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
TLS_DIR = os.environ.get("E2E_TLS_DIR", "")
REPORT = Path(os.environ.get("E2E_REPORT", Path(__file__).parent / "report.html"))
_results: list[tuple[str, str, str]] = []


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    missing = [
        n
        for n, v in (
            ("LM_DEMO", LM_DEMO),
            ("E2E_DATABASE_URL", DATABASE_URL),
            ("E2E_TLS_DIR", TLS_DIR),
        )
        if not v
    ]
    if missing:
        skip = pytest.mark.skip(reason=f"not set: {', '.join(missing)} (make e2e-stand)")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stand]:
    from stand import fresh_database

    url = fresh_database(DATABASE_URL, DATABASE_URL.rpartition("/")[2] or "almi_e2e")
    yield from start_server(tmp_path_factory.mktemp("stand"), url, Path(TLS_DIR))


@pytest.fixture
def stand(server: Stand) -> Iterator[Stand]:
    """Each scenario starts at the real time and leaves it there."""
    server.shift(0)
    yield server
    server.shift(0)


@pytest.fixture
def device(stand: Stand, tmp_path: Path) -> Device:
    return new_device(stand, tmp_path / "pc-1")


def new_device(stand: Stand, root: Path) -> Device:
    (root / "home").mkdir(parents=True)
    return Device(LM_DEMO, root / "data", stand.url, root / "home")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: Any) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        doc = getattr(getattr(item, "function", None), "__doc__", "") or ""
        _results.append((item.name, report.outcome, doc.strip()))


def pytest_sessionfinish(session: pytest.Session) -> None:
    if not _results:
        return
    rows = "".join(
        f"<tr class='{o}'><td>{html.escape(n)}</td><td>{o}</td>"
        f"<td><pre>{html.escape(d)}</pre></td></tr>"
        for n, o, d in _results
    )
    style = (
        "td{vertical-align:top;padding:4px 8px}.failed{background:#fdd}"
        ".passed{background:#dfd}.skipped{background:#eee}pre{margin:0;white-space:pre-wrap}"
    )
    REPORT.write_text(
        f"<!doctype html><meta charset='utf-8'><title>E2E stage 1</title><style>{style}</style>"
        "<h1>Сквозные сценарии этапа 1</h1>"
        f"<table><tr><th>Сценарий</th><th>Итог</th><th>Шаги</th></tr>{rows}</table>",
        encoding="utf-8",
    )


@pytest.fixture
def local_server(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Stand]:
    """A local server of the customer with its own database (scenarios 3 and 4)."""
    from stand import fresh_database

    url = fresh_database(DATABASE_URL, f"almi_e2e_local_{request.node.name[-20:].lower()}")
    root = tmp_path / "local-server"
    root.mkdir()
    yield from start_server(root, url, Path(TLS_DIR), mode="local")
