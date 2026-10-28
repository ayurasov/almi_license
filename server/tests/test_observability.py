"""E15-05: /metrics (requests, errors, duration, task queue) and JSON log lines."""

import json
import logging
import os
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client

from infra import metrics
from infra.clock import FrozenClock, use_clock
from infra.logs import JsonFormatter


@pytest.fixture(autouse=True)
def fresh() -> None:
    metrics.reset()


def test_metrics_count_requests_by_route(db: None) -> None:
    client = Client()
    client.get("/health")
    client.get("/health")
    client.get("/api/admin/licenses/00000000-0000-4000-8000-000000000001")  # 401, no session
    text = client.get("/metrics").content.decode()
    assert 'almi_http_requests_total{method="GET",route="health",status="200"} 2.0' in text
    # The route pattern, not the path with the id.
    assert 'route="api/admin/licenses/<uuid:license_id>",status="401"' in text
    assert "00000000-0000-4000-8000-000000000001" not in text
    assert 'almi_http_request_duration_seconds_bucket{le="+Inf",route="health"} 2.0' in text
    assert "# TYPE almi_http_request_duration_seconds histogram" in text


def test_metrics_of_the_task_queue(db: None, clock: FrozenClock) -> None:
    from apps.outbox.domain import enqueue

    enqueue("test.later", {}, now=clock.now() - timedelta(minutes=1))
    with use_clock(clock):
        text = Client().get("/metrics").content.decode()
    assert "almi_task_queue_due 1" in text
    assert "almi_task_failed 0" in text


def test_server_errors_are_counted() -> None:
    metrics.ERRORS.labels(route="api/v1/activations").inc()
    assert 'almi_http_errors_total{route="api/v1/activations"} 1.0' in metrics.render()


def test_workers_are_added_up(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gunicorn workers write their values to one directory; /metrics adds them up (question 42)."""
    import subprocess
    import sys

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    script = (
        "from infra import metrics; "
        "metrics.REQUESTS.labels(method='GET', route='health', status='200').inc()"
    )
    for _ in range(3):
        subprocess.run(  # noqa: S603 - a fixed script of this test
            [sys.executable, "-c", script], check=True, cwd=".", env=dict(os.environ)
        )
    assert 'almi_http_requests_total{method="GET",route="health",status="200"} 3.0' in (
        metrics.render()
    )


def test_json_log_line() -> None:
    record = logging.LogRecord(
        "apps.x", logging.WARNING, __file__, 1, "task %s failed", ("k",), None
    )
    try:
        raise ValueError("secret-looking text")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    line: dict[str, Any] = json.loads(JsonFormatter().format(record))
    assert (line["level"], line["logger"], line["message"]) == (
        "WARNING",
        "apps.x",
        "task k failed",
    )
    assert line["exception"] == "ValueError"
    assert "secret-looking" not in json.dumps(line)
    assert line["time"].endswith("Z")


def test_backup_age(db: None, clock: FrozenClock, settings: Any, tmp_path: Any) -> None:
    status = tmp_path / "last-success"
    settings.BACKUP_STATUS_FILE = str(status)
    with use_clock(clock):
        assert "almi_backup_age_seconds -1" in Client().get("/metrics").content.decode()
        status.write_text(str(int(clock.now().timestamp()) - 3600), encoding="ascii")
        assert "almi_backup_age_seconds 3600" in Client().get("/metrics").content.decode()


KEY = "-".join(("4426", "AB12", "CD34", "EF56"))  # the format of a key, not a real one


@pytest.mark.parametrize(
    ("message", "args", "expected"),
    [
        # uvicorn access line (gunicorn worker): the client, method, full path with the query.
        (
            '%s - "%s %s HTTP/%s" %d',
            ("10.0.0.5:0", "GET", f"/api/activate/?data=m&host=h&lic={KEY}", "1.1", 200),
            '10.0.0.5:0 - "GET /api/activate/?data=m&host=h&lic=*** HTTP/1.1" 200',
        ),
        # django.request on a 404 of the Nextcloud adapter: the key is a path segment.
        (
            "Not Found: %s",
            ("/apps/zammad_organisation_management/api/query/subscription/legacy-KEY-1",),
            "Not Found: /apps/zammad_organisation_management/api/query/subscription/***",
        ),
        ("activation of %s", (KEY,), "activation of ***"),
        ("nothing to hide: %s", ("act_01J",), "nothing to hide: act_01J"),
    ],
)
def test_licence_keys_are_masked_in_log_lines(message: str, args: Any, expected: str) -> None:
    """AGENTS.md, rule 9: the full licence key never reaches a log line (finding of v0.6.5)."""
    from infra.logs import RedactKeys

    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, message, args, None)
    assert RedactKeys().filter(record)
    assert record.getMessage() == expected


def test_key_filter_is_on_the_stdout_handler_and_the_workers() -> None:
    from almi_license import gunicorn_conf
    from infra.logs import RedactKeys

    [handler] = [h for h in logging.getLogger().handlers if isinstance(h.formatter, JsonFormatter)]
    assert any(isinstance(f, RedactKeys) for f in handler.filters)
    gunicorn_conf.post_worker_init(None)
    assert any(isinstance(f, RedactKeys) for f in logging.getLogger("uvicorn.access").filters)


def test_every_answer_has_server_time_and_request_id(db: None, clock: FrozenClock) -> None:
    """Section 4.3 of document 2: ALMI-Server-Time always; X-Request-Id is returned or made."""
    with use_clock(clock):
        answer = Client().get("/health")
        problem = Client().post(
            "/api/v1/activations", data="{}", content_type="application/json",
            headers={"X-Request-Id": "req-42"},
        )  # fmt: skip
    assert answer["ALMI-Server-Time"] == "2026-11-02T08:15:00Z"
    assert len(answer["X-Request-Id"]) == 26
    assert problem["X-Request-Id"] == "req-42" and problem.json()["request_id"] == "req-42"
    assert problem["ALMI-Server-Time"] == "2026-11-02T08:15:00Z"
